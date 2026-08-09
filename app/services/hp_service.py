"""
HP Service — central authority for all Holy Points operations.

EARNING RULES (Master Brand Document — final):
  Food order:     1 HP per ₦10 → ACTIVE + tier multiplier bonus → ACTIVE
  Welcome bonus:  50 HP → ACTIVE (first order only)
  Referral:       75 HP → ACTIVE (no per-month cap), milestones 5×→+150, 10×→+400
  Event check-in: 40 HP → PENDING (no per-month cap)
  Review:         20 HP → PENDING (no per-month cap)
  Birthday:       150 HP → ACTIVE (30-day window)
  Wallet top-up:  50 HP → ACTIVE (≥ ₦3,000 only)
  Social share:   25 HP → PENDING (per valid share)
  Pending ceiling: 800 HP maximum in pending pool at any time

UNLOCK MECHANIC:
  Unlock = food_spend × HP_PER_NAIRA_FOOD × HP_UNLOCK_RATE_PCT
  (e.g. ₦1,000 × 0.1 × 0.30 = 30 HP unlocked per ₦1,000 food spend)

TIER SYSTEM (rolling 120-day hp_earned):
  Ember/Starter: 0 HP        multiplier 1.00
  Flame:         2,500 HP    multiplier 1.08
  Blaze/Inferno: 7,500 HP    multiplier 1.15
  Holy:          20,000 HP   multiplier 1.25
  Grace period: 7 days before downgrade

HP TRANSACTION TYPE ENUM VALUES (from live DB — confirmed):
  ONLY 3 valid values: earn | spend | expire
  Direction is set by `type`; what it was for is captured in `source` column.
  Common source values: food_order, welcome, referral, review, spin_wheel,
    unlock, admin_grant, event_checkin, birthday, challenge, expiry
"""

import math
from datetime import datetime, timezone, timedelta
from app.db import get_db, SupabaseError
from flask import current_app


# ── Enum type mapping (source_type → hp_transaction_type enum value) ─────────
TXN_TYPE_MAP = {
    "food":             "earn_order",
    "order":            "earn_order",
    "welcome":          "earn_first_order",
    "welcome_bonus":    "earn_first_order",
    "first_order":      "earn_first_order",
    "referral":         "earn_referral",
    "event":            "earn_event_checkin",
    "event_checkin":    "earn_event_checkin",
    "review":           "earn_review",
    "birthday":         "earn_birthday",
    "challenge":        "earn_challenge",
    "admin_grant":      "earn_admin_grant",
    "bundle_purchase":  "earn_admin_grant",
    "squad_bonus":      "earn_squad_bonus",
    "streak":           "earn_streak",
    "wallet_topup":     "earn_admin_grant",
    "newsletter":       "earn_admin_grant",
    "social":           "earn_challenge",
    "unlock":           "unlock",
    "overflow_to_pending": "overflow_to_pending",
    # transfers
    "hp_transfer":           "earn_admin_grant",
    "earn_transfer":         "earn_admin_grant",
    # spending
    "spend_reward":          "spend_reward",
    "reward_redemption":     "spend_reward",
    "flash_reward_redemption": "spend_reward",
    "spend_marketplace":     "spend_marketplace",
    "marketplace_purchase":  "spend_marketplace",
    "spend_order_discount":  "spend_order_discount",
    "order_hp_redemption":   "spend_order_discount",
    "expiry":                "expire",
}

def _resolve_txn_type(source_type: str, is_spend: bool = False, is_unlock: bool = False) -> str:
    """Map a source_type to a DB-valid type: 'earn' | 'spend' | 'expire'.
    'unlock' is not a valid DB enum value — treated as 'earn'.
    """
    if source_type in {"expiry", "expire"}:
        return "expire"
    if is_spend or source_type in {
        "spend_reward", "reward_redemption", "flash_reward_redemption",
        "spend_marketplace", "marketplace_purchase",
        "spend_order_discount", "order_hp_redemption",
        "spin_cost",
    }:
        return "spend"
    return "earn"


def get_hp_balance(user_id: str) -> dict:
    """
    Fetch HP balance from profiles.hp_balance (authoritative active balance).
    Pending HP is tracked via hp_transactions rows where status='pending'.
    hp_earned_120day is read from profiles.hp_earned_120day (updated by daily task).
    """
    db = get_db()
    try:
        profile = (
            db.table("profiles")
            .select("hp_balance,hp_earned_120day")
            .eq("id", user_id)
            .single()
            .execute()
        )
    except SupabaseError:
        profile = {}

    active = int(profile.get("hp_balance") or 0)
    hp_earned_120day = int(profile.get("hp_earned_120day") or 0)

    try:
        pending_rows = (
            db.table("hp_transactions")
            .select("amount")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .execute()
        )
        pending = sum(int(r.get("amount", 0)) for r in (pending_rows or []))
    except Exception:
        pending = 0

    tier_info = None
    try:
        tier_info = get_user_tier(user_id)
    except Exception:
        pass

    multiplier = 1.0
    try:
        t = (tier_info or {}).get("tier") or {}
        multiplier = float(t.get("earn_multiplier") or 1.0)
    except Exception:
        pass

    return {
        "active": max(0, active),
        "pending": max(0, pending),
        "total_visible": max(0, active + pending),
        "monthly_hp_earned": 0,
        "hp_earned_120day": max(0, hp_earned_120day),
        "tier_bonus_multiplier": multiplier,
        "tier": tier_info,
    }


def _get_hp_multiplier() -> float:
    """
    Read the active HP earn multiplier from system_settings.
    Only the supported 2x event is accepted. Returns 1.0 if disabled,
    expired, or if a stale/invalid value (including 0.5) is found.
    """
    try:
        db = get_db()
        m_row = db.table("system_settings").select("value").eq("key", "hp_multiplier").single().execute()
        multiplier = float((m_row or {}).get("value", "1") or "1")
        if multiplier != 2.0:
            return 1.0
        # Check expiry
        exp_row = db.table("system_settings").select("value").eq("key", "multiplier_expires_at").single().execute()
        expires_at = ((exp_row or {}).get("value") or "").strip()
        if expires_at:
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp_dt:
                return 1.0
        return multiplier
    except Exception:
        return 1.0


def award_food_order_hp(
    user_id: str,
    order_id: str,
    order_total: float,
    tier_slug: str = "ember",
    order_items: list | None = None,
) -> dict:
    """
    Award HP for a completed food order.
    ALL food HP goes to ACTIVE balance.
    Applies HP multiplier if active.
    Also triggers FIFO pending-pool unlock.

    Returns: base_hp, tier_bonus_hp, total_hp, unlocked_pending_hp
    """
    config = current_app.config
    tier_multiplier = config.get("TIER_MULTIPLIERS", {}).get(tier_slug.lower(), 1.0)
    if order_items:
        base_hp = 0
        multiplied_base_hp = 0
        total_hp = 0
        for item in order_items:
            if item.get("is_addon") or not item.get("price_snapshot"):
                continue
            line_base_hp = int(
                float(item.get("price_snapshot") or 0)
                * int(item.get("quantity") or 1)
                * config["HP_PER_NAIRA_FOOD"]
            )
            base_hp += line_base_hp
            try:
                item_multiplier = float(item.get("hp_multiplier_snapshot") or 1.0)
            except (TypeError, ValueError):
                item_multiplier = 1.0
            if item_multiplier not in (0.5, 1.0, 2.0):
                item_multiplier = 1.0
            multiplied_line_hp = round(line_base_hp * item_multiplier)
            multiplied_base_hp += multiplied_line_hp
            total_hp += round(multiplied_line_hp * tier_multiplier)
        tier_bonus_hp = total_hp - multiplied_base_hp
        event_multiplier = 1.0
    else:
        # Legacy callers without line snapshots retain the historical
        # order-level behavior until all delivery paths pass order_items.
        base_hp = int(order_total * config["HP_PER_NAIRA_FOOD"])
        tier_bonus_hp = round(base_hp * (tier_multiplier - 1.0))
        event_multiplier = _get_hp_multiplier()
        total_hp = round(base_hp * event_multiplier) + tier_bonus_hp

    if total_hp > 0:
        _record_hp_transaction(
            user_id=user_id,
            amount=total_hp,
            txn_type="earn",
            reference_id=order_id,
            reference_type="order",
            source_type="food",
            notes=(
                f"Food order HP: {base_hp} base"
                + (" × per-item multiplier" if order_items else
                   (f" ×{event_multiplier} multiplier" if event_multiplier > 1.0 else ""))
                + f" + {tier_bonus_hp} tier bonus ({tier_slug})"
            ),
            status="active",
        )
        _update_earned_counters(user_id, total_hp)

    unlock_result = unlock_pending_hp(user_id, order_id, order_total)
    return {
        "base_hp": base_hp,
        "tier_bonus_hp": tier_bonus_hp,
        "total_hp": total_hp,
        "unlocked_pending_hp": unlock_result.get("unlocked", 0),
        "multiplier_applied": event_multiplier,
    }


def unlock_pending_hp(user_id: str, order_id: str, food_spend: float) -> dict:
    """
    Unlock pending HP proportional to food spend — FIFO.
    Formula: floor(food_spend × HP_PER_NAIRA_FOOD × HP_UNLOCK_RATE_PCT)
    = 30% of the order's BASE food HP (no tier bonus, no multiplier).

    Converts the oldest pending HP transactions to active status (FIFO).
    Updates profiles.hp_balance for each converted amount.
    """
    config = current_app.config
    amount_to_unlock = math.floor(
        food_spend * config["HP_PER_NAIRA_FOOD"] * config.get("HP_UNLOCK_RATE_PCT", 0.30)
    )
    if amount_to_unlock <= 0:
        return {"unlocked": 0}

    db = get_db()

    # Fetch oldest pending transactions (FIFO order)
    try:
        pending_txns = (
            db.table("hp_transactions")
            .select("id,amount")
            .eq("user_id", user_id)
            .eq("status", "pending")
            .order("created_at", ascending=True)
            .execute()
        ) or []
    except Exception:
        pending_txns = []

    remaining = amount_to_unlock
    total_unlocked = 0
    now = datetime.now(timezone.utc).isoformat()

    for txn in pending_txns:
        if remaining <= 0:
            break
        txn_amount = int(txn.get("amount", 0))
        if txn_amount <= 0:
            continue

        try:
            if txn_amount <= remaining:
                # Convert entire pending transaction → active
                db.table("hp_transactions").eq("id", txn["id"]).update({"status": "active"})
                # Increment profile balance
                profile = db.table("profiles").select("hp_balance").eq("id", user_id).single().execute()
                current_bal = int((profile or {}).get("hp_balance") or 0)
                new_bal = max(0, current_bal + txn_amount)
                db.table("profiles").eq("id", user_id).update({"hp_balance": new_bal})
                total_unlocked += txn_amount
                remaining -= txn_amount
            else:
                # Split: create a new active transaction for `remaining`, shrink the pending one
                new_pending_amount = txn_amount - remaining
                db.table("hp_transactions").eq("id", txn["id"]).update({"amount": new_pending_amount})
                # Record the unlocked portion as a new active transaction
                _record_hp_transaction(
                    user_id=user_id,
                    amount=remaining,
                    txn_type="earn",
                    reference_id=order_id,
                    reference_type="order",
                    source_type="unlock",
                    notes=f"Pending HP unlocked (FIFO split): {remaining} HP → active",
                    status="active",
                )
                total_unlocked += remaining
                remaining = 0
        except Exception as e:
            logger.warning("unlock_pending_hp: FIFO convert error for txn %s: %s", txn.get("id"), e)
            continue

    if total_unlocked > 0:
        try:
            recalculate_tier(user_id)
        except Exception:
            pass

    return {"unlocked": total_unlocked}


import logging as _logging
logger = _logging.getLogger(__name__)


def earn_pending_hp(user_id: str, amount: int, source_type: str, reference_id: str = None, notes: str = "") -> dict:
    """
    Add HP to pending pool.
    Referral HP goes to ACTIVE (referral → active per brand spec).
    All other source types (event, review, challenge, social, bundle_purchase) → pending.
    HP multiplier is applied to all HP earning.
    """
    if amount <= 0:
        return {"added_to_pending": 0, "added_to_overflow": 0, "source_type": source_type}

    # Apply multiplier
    multiplier = _get_hp_multiplier()
    if multiplier > 1.0:
        amount = round(amount * multiplier)

    is_referral = source_type in ("referral", "earn_referral")
    status = "active" if is_referral else "pending"

    txn_type = _resolve_txn_type(source_type)
    _record_hp_transaction(
        user_id=user_id,
        amount=amount,
        txn_type=txn_type,
        reference_id=reference_id,
        reference_type=source_type,
        source_type=source_type,
        notes=notes or f"{source_type} HP → {status}" + (f" (×{multiplier} multiplier)" if multiplier > 1.0 else ""),
        status=status,
    )
    if is_referral:
        _update_earned_counters(user_id, amount)
    return {
        "added_to_pending": 0 if is_referral else amount,
        "added_to_overflow": 0,
        "source_type": source_type,
    }


def award_active_hp(
    user_id: str,
    amount: int,
    txn_type: str = None,
    reference_id: str = None,
    reference_type: str = None,
    source_type: str = None,
    notes: str = "",
    issued_by_admin_id: str = None,
    apply_multiplier: bool = True,
) -> dict:
    """
    Directly award HP to ACTIVE balance.
    Used for: welcome_bonus, birthday, wallet_topup, newsletter, admin_grant, milestone bonuses.
    Admin reversals (negative amount) are allowed when issued_by_admin_id is provided.
    apply_multiplier=False for admin grants and system corrections.
    """
    if amount == 0:
        return {"awarded": 0}
    if amount < 0 and not issued_by_admin_id:
        return {"awarded": 0}

    # Apply multiplier for positive earnings (not admin grants or reversals)
    original_amount = amount
    if amount > 0 and apply_multiplier and not issued_by_admin_id:
        multiplier = _get_hp_multiplier()
        if multiplier > 1.0:
            amount = round(amount * multiplier)

    resolved_type = txn_type or _resolve_txn_type(source_type or reference_type or "admin_grant")
    _record_hp_transaction(
        user_id=user_id,
        amount=amount,
        txn_type=resolved_type,
        reference_id=reference_id,
        reference_type=reference_type,
        source_type=source_type or reference_type,
        notes=notes + (f" (×{round(amount / original_amount, 2)} multiplier)" if amount != original_amount and notes else ""),
        status="active",
        issued_by_admin_id=issued_by_admin_id,
    )
    _update_earned_counters(user_id, amount)
    return {"awarded": amount}


def spend_hp(user_id: str, amount: int, reference_id: str, reference_type: str, notes: str = "") -> dict:
    """Deduct HP from active balance. Raises ValueError if insufficient."""
    balance = get_hp_balance(user_id)
    if balance["active"] < amount:
        from app.messages import MSG, resolve_msg
        raise ValueError(resolve_msg(MSG.HP_INSUFFICIENT, have=balance["active"], need=amount))

    txn_type = _resolve_txn_type(reference_type, is_spend=True)
    _record_hp_transaction(
        user_id=user_id,
        amount=-amount,
        txn_type=txn_type,
        reference_id=reference_id,
        reference_type=reference_type,
        source_type=reference_type,
        notes=notes or f"HP spent on {reference_type}",
        status="active",
    )
    return {"spent": amount, "balance_after": balance["active"] - amount}


def expire_hp(user_id: str, amount: int, notes: str = "HP decayed due to inactivity") -> dict:
    """Apply HP decay. Deducts from active balance."""
    balance = get_hp_balance(user_id)
    expire_amount = min(amount, max(0, balance["active"]))
    if expire_amount <= 0:
        return {"expired": 0}
    _record_hp_transaction(
        user_id=user_id,
        amount=-expire_amount,
        txn_type="expire",
        reference_id=None,
        reference_type="expiry",
        source_type="expiry",
        notes=notes,
        status="active",
    )
    return {"expired": expire_amount}


def award_signup_bonus(user_id: str) -> dict:
    """Grant SIGNUP_BONUS_HP active HP on account creation. No-op when amount is 0."""
    amount = current_app.config.get("SIGNUP_BONUS_HP", 0)
    if not amount:
        return {"awarded": 0, "reason": "Signup bonus disabled"}
    db = get_db()
    already = (
        db.table("hp_transactions")
        .select("id")
        .eq("user_id", user_id)
        .eq("source", "signup")
        .execute()
    )
    if already:
        return {"awarded": 0, "reason": "Already received"}
    return award_active_hp(
        user_id=user_id,
        amount=amount,
        txn_type="earn",
        reference_id=user_id,
        reference_type="signup_bonus",
        source_type="signup",
        notes=f"Welcome to {current_app.config.get('APP_NAME', 'Holy Grills')} — {amount} HP signup gift",
    )


def award_welcome_bonus(user_id: str, order_id: str) -> dict:
    """Award WELCOME_BONUS_HP active HP on the user's first delivered order. Checks if already awarded."""
    db = get_db()
    already = (
        db.table("hp_transactions")
        .select("id")
        .eq("user_id", user_id)
        .eq("source", "welcome")
        .execute()
    )
    if already:
        return {"awarded": 0, "reason": "Already received"}
    amount = current_app.config["WELCOME_BONUS_HP"]
    return award_active_hp(
        user_id=user_id,
        amount=amount,
        txn_type="earn",
        reference_id=order_id,
        reference_type="welcome_bonus",
        source_type="welcome",
        notes=f"Welcome bonus — {amount} HP on first order",
    )


def get_user_tier(user_id: str) -> dict:
    """Get user's current tier from profiles.current_tier_id → hp_tiers."""
    db = get_db()
    try:
        profile = (
            db.table("profiles")
            .select("current_tier_id,tier_grace_ends_at,tier_grace_started_at")
            .eq("id", user_id)
            .single()
            .execute()
        )
        tier_id = profile.get("current_tier_id") if profile else None
        if not tier_id:
            base_tiers = (
                db.table("hp_tiers")
                .select("*")
                .eq("is_active", "true")
                .order("sort_order")
                .limit(1)
                .execute()
            )
            return {"tier": base_tiers[0] if base_tiers else None, "is_in_grace_period": False}

        tier = db.table("hp_tiers").select("*").eq("id", tier_id).single().execute()
        grace_ends = profile.get("tier_grace_ends_at")
        now_iso = datetime.now(timezone.utc).isoformat()
        is_in_grace = bool(grace_ends and grace_ends > now_iso)
        return {
            "tier": tier,
            "is_in_grace_period": is_in_grace,
            "grace_period_ends_at": grace_ends,
        }
    except Exception:
        return {"tier": None, "is_in_grace_period": False}


def recalculate_tier(user_id: str) -> dict:
    """
    Compare hp_earned_120day against tier thresholds (min_points column in hp_tiers).
    Uses the rolling 120-day earned HP — not the current balance — to determine tier.
    Updates profiles.current_tier_id and logs to user_tiers (event log).
    """
    db = get_db()
    try:
        profile = (
            db.table("profiles")
            .select("hp_earned_120day,current_tier_id")
            .eq("id", user_id)
            .single()
            .execute()
        )
        hp_earned_120day = int(profile.get("hp_earned_120day") or 0)
        current_tier_id = profile.get("current_tier_id")
    except Exception:
        hp_earned_120day = 0
        current_tier_id = None

    tiers_raw = (
        db.table("hp_tiers")
        .select("*")
        .eq("is_active", "true")
        .order("sort_order", ascending=False)
        .execute()
    )
    tiers = sorted(tiers_raw or [], key=lambda t: int(t.get("min_points") or 0), reverse=True)
    new_tier = None
    for tier in tiers:
        if hp_earned_120day >= int(tier.get("min_points") or 0):
            new_tier = tier
            break
    if not new_tier and tiers:
        new_tier = tiers[-1]

    if not new_tier:
        return {"tier": None, "changed": False}

    if current_tier_id == new_tier["id"]:
        return {"tier": new_tier, "changed": False}

    event = "upgraded" if (not current_tier_id or _tier_sort_order(new_tier) > _tier_sort_order_by_id(current_tier_id, tiers_raw)) else "downgraded"
    try:
        db.table("user_tiers").insert({
            "user_id": user_id,
            "tier_id": new_tier["id"],
            "previous_tier_id": current_tier_id,
            "event": event,
            "hp_at_event": hp_earned_120day,
        })
    except Exception:
        pass

    try:
        db.table("profiles").eq("id", user_id).update({"current_tier_id": new_tier["id"]})
    except Exception:
        pass

    return {"tier": new_tier, "changed": True, "previous_tier_id": current_tier_id, "event": event}


def _tier_sort_order(tier: dict) -> int:
    return int(tier.get("sort_order") or 0)


def _tier_sort_order_by_id(tier_id: str, tiers: list) -> int:
    t = next((t for t in (tiers or []) if t.get("id") == tier_id), None)
    return int(t.get("sort_order") or 0) if t else 0


def process_flash_redeem(reward_id: str, user_id: str) -> dict:
    """Flash redemption: 50% HP discount, first N users only, 24-hour window."""
    db = get_db()
    config = current_app.config

    flash = (
        db.table("flash_redemptions")
        .select("*")
        .eq("reward_id", reward_id)
        .eq("is_active", "true")
        .single()
        .execute()
    )
    if not flash:
        from app.messages import MSG
        raise ValueError(MSG.HP_FLASH_NO_ACTIVE_SALE)

    now = datetime.now(timezone.utc).isoformat()
    if flash.get("window_ends_at") and flash["window_ends_at"] < now:
        from app.messages import MSG
        raise ValueError(MSG.HP_FLASH_WINDOW_CLOSED)

    already_redeemed = (
        db.table("reward_redemptions")
        .select("id")
        .eq("reward_id", reward_id)
        .gte("created_at", flash.get("window_starts_at", ""))
        .execute()
    )
    qty_limit = flash.get("quantity_limit", config.get("FLASH_MAX_QTY", 5))
    if len(already_redeemed) >= qty_limit:
        from app.messages import MSG
        raise ValueError(MSG.HP_FLASH_LIMIT_REACHED.format(qty=qty_limit))

    reward = db.table("rewards").select("hp_cost,name").eq("id", reward_id).single().execute()
    original_cost = reward.get("hp_cost", 0)
    discounted_cost = int(original_cost * (1 - config.get("FLASH_DISCOUNT_PCT", 0.5)))

    balance = get_hp_balance(user_id)
    if balance["active"] < discounted_cost:
        from app.messages import MSG, resolve_msg
        raise ValueError(resolve_msg(MSG.HP_FLASH_INSUFFICIENT, need=discounted_cost, have=balance["active"]))

    redemption = db.table("reward_redemptions").insert({
        "user_id": user_id,
        "reward_id": reward_id,
        "hp_cost_snapshot": discounted_cost,
        "status": "pending",
    })
    redemption_row = redemption[0] if isinstance(redemption, list) else redemption

    spend_hp(user_id, discounted_cost, redemption_row["id"], "flash_reward_redemption",
             f"Flash deal: {reward.get('name')} at 50% off")

    return {
        "redemption": redemption_row,
        "original_hp_cost": original_cost,
        "discounted_hp_cost": discounted_cost,
        "savings_hp": original_cost - discounted_cost,
    }


def process_hp_bundle_purchase(event_host_id: str, hp_amount: int, naira_paid: float) -> dict:
    """Event hosts purchase HP bundles at ₦5/HP. HP credited to pending pool."""
    config = current_app.config
    price_per_hp = config.get("HP_BUNDLE_PRICE_PER_HP", 5.0)
    expected_naira = hp_amount * price_per_hp
    if abs(naira_paid - expected_naira) > 1:
        raise ValueError(f"Payment mismatch: ₦{naira_paid} received, ₦{expected_naira} expected")

    db = get_db()
    try:
        db.table("hp_bundle_purchases").insert({
            "event_host_id": event_host_id,
            "hp_amount": hp_amount,
            "naira_paid": naira_paid,
            "price_per_hp": price_per_hp,
        })
    except Exception:
        pass

    result = earn_pending_hp(
        user_id=event_host_id,
        amount=hp_amount,
        source_type="bundle_purchase",
        notes=f"HP bundle: {hp_amount} HP at ₦{price_per_hp}/HP (₦{naira_paid:.0f} total)",
    )
    return {"hp_credited_to_pending": result["added_to_pending"], "hp_to_overflow": result["added_to_overflow"]}



# ── Internal helpers ──────────────────────────────────────────────────────────

def _record_hp_transaction(
    user_id: str,
    amount: int,
    txn_type: str,
    reference_id: str = None,
    reference_type: str = None,
    source_type: str = None,
    notes: str = "",
    status: str = "active",
    issued_by_admin_id: str = None,
):
    db = get_db()
    balance = get_hp_balance(user_id)

    # Pending HP does NOT change the active balance — only active/spend/expire do
    if status == "pending":
        balance_after = max(0, balance["active"])
    elif txn_type == "spend" or (amount < 0):
        balance_after = max(0, balance["active"] - abs(amount))
    else:
        balance_after = max(0, balance["active"] + abs(amount))

    resolved_source = source_type or reference_type or "system"
    record = {
        "user_id": user_id,
        "amount": abs(amount),
        "type": txn_type,
        "status": status,
        "balance_after": balance_after,
        "source": resolved_source,
        "metadata": {"notes": notes} if notes else {},
    }
    if reference_id:
        record["reference_id"] = reference_id
    if reference_type:
        record["reference_type"] = reference_type
    if issued_by_admin_id:
        record["issued_by_admin_id"] = issued_by_admin_id

    try:
        db.table("hp_transactions").insert(record)
    except SupabaseError:
        # Fallback without metadata in case that column has a type mismatch
        basic = {
            "user_id": user_id,
            "amount": abs(amount),
            "type": txn_type,
            "status": status,
            "balance_after": balance_after,
            "source": resolved_source,
        }
        if reference_id:
            basic["reference_id"] = reference_id
        if reference_type:
            basic["reference_type"] = reference_type
        if issued_by_admin_id:
            basic["issued_by_admin_id"] = issued_by_admin_id
        try:
            db.table("hp_transactions").insert(basic)
        except SupabaseError:
            pass

    # Only update profiles.hp_balance when this is an active change
    if status != "pending":
        try:
            db.table("profiles").eq("id", user_id).update({"hp_balance": balance_after})
        except Exception:
            pass

    # Recalculate tier whenever active HP changes
    if status != "pending":
        try:
            recalculate_tier(user_id)
        except Exception:
            pass


def _update_earned_counters(user_id: str, amount: int):
    """
    Increment the current month's HP earned counter in monthly_hp_tracker.
    Uses read-then-upsert: reads current total, adds amount, then upserts.
    The monthly_hp_tracker table must have a UNIQUE constraint on (user_id, month)
    (see sql_migrations.sql) so concurrent upserts resolve cleanly.
    Used for: monthly leaderboard accuracy, per-user monthly HP cap enforcement.
    Skips gracefully if the table doesn't exist yet.
    """
    if amount <= 0:
        return
    db = get_db()
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    try:
        existing = (
            db.table("monthly_hp_tracker")
            .select("id,total_earned")
            .eq("user_id", user_id)
            .eq("month", month)
            .single()
            .execute()
        )
        current_total = int((existing or {}).get("total_earned") or 0)
        new_total = current_total + amount
        # Upsert on the unique (user_id, month) constraint — avoids duplicate rows
        db.table("monthly_hp_tracker").upsert({
            "user_id": user_id,
            "month": month,
            "total_earned": new_total,
            "updated_at": now.isoformat(),
        }, on_conflict="user_id,month")
    except Exception:
        pass


def _get_profile_hp_fields(user_id: str) -> dict:
    db = get_db()
    try:
        return (
            db.table("profiles")
            .select("hp_balance")
            .eq("id", user_id)
            .single()
            .execute()
        ) or {}
    except Exception:
        return {}


def _safe_update_profile(user_id: str, updates: dict):
    """Update profile, stripping unknown columns on failure."""
    db = get_db()
    safe_fields = {"hp_balance", "updated_at"}
    safe_updates = {k: v for k, v in updates.items() if k in safe_fields}
    if safe_updates:
        try:
            db.table("profiles").eq("id", user_id).update(safe_updates)
        except Exception:
            pass
