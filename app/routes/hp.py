"""HP (Holy Points) routes — balance, transactions, history."""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role
from app.services.hp_service import (
    get_hp_balance, get_user_tier, spend_hp, earn_pending_hp, award_active_hp
)
from app.db import get_db
from app.messages import MSG, resolve_msg

hp_bp = Blueprint("hp", __name__)


@hp_bp.route("/balance", methods=["GET"])
@require_auth
def balance():
    """
    Get user's HP balance: active, pending, total_visible.
    HP value in ₦ terms is NOT returned (internal admin/analytics only).
    ---
    tags: [HP]
    responses:
      200:
        description: HP balance breakdown
    """
    bal = get_hp_balance(g.user_id)
    tier = get_user_tier(g.user_id)
    # §24: overflow field removed. §15: no HP→₦ conversion in user-facing response.
    safe_bal = {k: v for k, v in bal.items() if k not in ("overflow", "overflow_hp", "hp_naira_value")}
    return jsonify({**safe_bal, "tier": tier}), 200


@hp_bp.route("/transactions", methods=["GET"])
@require_auth
def transactions():
    """
    Get HP transaction history for the authenticated user.
    ---
    tags: [HP]
    parameters:
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
      - in: query
        name: type
        type: string
        description: Filter by transaction type
    responses:
      200:
        description: HP transaction list
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("hp_transactions").select("*").eq("user_id", g.user_id)
    txn_type = request.args.get("type")
    if txn_type:
        q = q.eq("type", txn_type)
    txns = q.order("created_at", ascending=False).limit(limit).offset(offset).execute()
    return jsonify(txns), 200


@hp_bp.route("/tiers", methods=["GET"])
def list_tiers():
    """
    List all tiers with thresholds and perks.
    ---
    tags: [HP]
    security: []
    responses:
      200:
        description: All tier definitions
    """
    db = get_db()
    tiers = db.table("hp_tiers").select("*").order("sort_order").execute()
    return jsonify(tiers), 200


@hp_bp.route("/admin/grant", methods=["POST"])
@require_role("admin")
def admin_grant():
    """
    Admin manually grants HP to a user.
    ---
    tags: [HP]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [user_id, amount]
          properties:
            user_id: {type: string}
            amount: {type: integer}
            notes: {type: string}
    responses:
      200:
        description: HP granted
    """
    data = request.get_json(force=True)
    if not data.get("user_id") or not data.get("amount"):
        return jsonify({"error": MSG.HP_ADMIN_REQUIRED_FIELDS}), 400

    try:
        result = award_active_hp(
            user_id=data["user_id"],
            amount=int(data["amount"]),
            txn_type="earn_admin_grant",
            notes=data.get("notes", "Admin-issued HP"),
            issued_by_admin_id=g.user_id,
        )
        _log_admin_action(g.user_id, "profiles", data["user_id"], "hp_grant", {"amount": data["amount"]})
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@hp_bp.route("/admin/expire", methods=["POST"])
@require_role("admin")
def admin_expire():
    """
    Admin manually expires HP for a user.
    ---
    tags: [HP]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [user_id, amount]
          properties:
            user_id: {type: string}
            amount: {type: integer}
            notes: {type: string}
    responses:
      200:
        description: HP expired
    """
    from app.services.hp_service import expire_hp, get_hp_balance
    data = request.get_json(force=True) or {}
    if not data.get("user_id"):
        return jsonify({"error": MSG.HP_ADMIN_REQUIRED_FIELDS}), 400
    amount = data.get("amount")
    if amount is None:
        # Expire all active HP if amount not specified
        balance = get_hp_balance(data["user_id"])
        amount = int(balance.get("active", 0))
    if amount <= 0:
        return jsonify({"message": "No active HP to expire", "expired": 0}), 200
    result = expire_hp(data["user_id"], int(amount), data.get("notes", "Manual HP expiry"))
    return jsonify(result), 200


@hp_bp.route("/flash-redeem/<reward_id>", methods=["POST"])
@require_auth
def flash_redeem(reward_id):
    """
    Redeem a reward at the flash-sale price (50% HP discount, limited slots, 24h window).

    Checks for an active flash_redemptions record linked to the reward, verifies
    the user has enough HP at the discounted rate, and calls process_flash_redeem
    from hp_service to deduct HP and record the redemption.
    ---
    tags: [HP]
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
    responses:
      200:
        description: Flash redemption successful
      400:
        description: No active flash sale, sold out, insufficient HP, or window closed
    """
    from app.services.hp_service import process_flash_redeem
    try:
        result = process_flash_redeem(reward_id=reward_id, user_id=g.user_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@hp_bp.route("/unlock-history", methods=["GET"])
@require_auth
def unlock_history():
    """
    Get HP unlock history for the authenticated user (from hp_transactions type=unlock).
    ---
    tags: [HP]
    parameters:
      - in: query
        name: limit
        type: integer
        default: 50
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: HP unlock log entries
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    rows = (
        db.table("hp_transactions")
        .select("*")
        .eq("user_id", g.user_id)
        .eq("type", "unlock")
        .order("created_at", ascending=False)
        .limit(limit)
        .offset(offset)
        .execute()
    )
    return jsonify(rows or []), 200


@hp_bp.route("/bundles", methods=["GET"])
def list_hp_bundles():
    """
    List available HP bundle tiers that can be purchased.
    ---
    tags: [HP]
    responses:
      200:
        description: List of HP bundle options with naira pricing
    """
    price_per_hp = float(current_app.config.get("HP_BUNDLE_PRICE_PER_HP", 5.0))
    min_purchase = int(current_app.config.get("HP_BUNDLE_MIN_PURCHASE", 100))
    # Bundle tiers are configured via HP_BUNDLES (JSON) in config / env so they
    # can be changed without a deploy. Each entry must have {hp, label}.
    bundles_config = current_app.config.get("HP_BUNDLES") or [
        {"hp": 100,  "label": "Starter"},
        {"hp": 250,  "label": "Basic"},
        {"hp": 500,  "label": "Standard"},
        {"hp": 1000, "label": "Premium"},
        {"hp": 2500, "label": "Elite"},
    ]
    bundles = [
        {"hp": b["hp"], "naira": round(b["hp"] * price_per_hp, 2), "label": b["label"]}
        for b in bundles_config
        if isinstance(b, dict) and int(b.get("hp", 0)) >= min_purchase
    ]
    return jsonify({
        "bundles": bundles,
        "price_per_hp": price_per_hp,
        "min_purchase_hp": min_purchase,
        "currency": "NGN",
    }), 200


@hp_bp.route("/bundles/purchase", methods=["POST"])
@require_auth
def purchase_hp_bundle():
    """
    Purchase an HP bundle (event hosts). Charges card via Paystack reference, credits HP.
    ---
    tags: [HP]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [hp_amount, paystack_reference]
          properties:
            hp_amount: {type: integer, minimum: 100, example: 500}
            paystack_reference: {type: string}
    responses:
      201:
        description: HP bundle purchased and credited
      400:
        description: Validation error
    """
    from app.services.hp_service import process_hp_bundle_purchase
    data = request.get_json(force=True)
    hp_amount = int(data.get("hp_amount", 0))
    reference = data.get("paystack_reference", "").strip()

    min_purchase = int(current_app.config.get("HP_BUNDLE_MIN_PURCHASE", 100))
    if hp_amount < min_purchase:
        return jsonify({"error": resolve_msg(MSG.HP_BUNDLE_MIN, min_hp=min_purchase)}), 400
    if not reference:
        return jsonify({"error": MSG.HP_BUNDLE_REF_REQUIRED}), 400

    price_per_hp = float(current_app.config.get("HP_BUNDLE_PRICE_PER_HP", 5.0))
    naira_paid = hp_amount * price_per_hp

    try:
        from app.services.payment_service import verify_payment
        txn_data = verify_payment(reference)
        if txn_data.get("status") != "success":
            return jsonify({"error": MSG.HP_PAYMENT_NOT_CONFIRMED.format(status=txn_data.get("status"))}), 402
        paid_kobo = txn_data.get("amount", 0)
        expected_kobo = int(naira_paid * 100)
        if paid_kobo < expected_kobo:
            return jsonify({"error": MSG.HP_PAYMENT_MISMATCH.format(expected=naira_paid, received=paid_kobo / 100)}), 402
    except Exception as e:
        return jsonify({"error": MSG.HP_PAYMENT_VERIFY_FAILED.format(error=str(e))}), 402

    try:
        result = process_hp_bundle_purchase(
            event_host_id=g.user_id,
            hp_amount=hp_amount,
            naira_paid=naira_paid,
        )
        return jsonify(result), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@hp_bp.route("/transfer", methods=["POST"])
@require_auth
def transfer_hp():
    """
    Transfer active HP to another user.
    ---
    tags: [HP]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [recipient_id, amount]
          properties:
            recipient_id:
              type: string
              description: UUID of the recipient user
            amount:
              type: integer
              description: HP amount to transfer
            notes:
              type: string
              description: Optional message to recipient
    responses:
      200:
        description: Transfer successful
      400:
        description: Insufficient HP, self-transfer, or minimum not met
      404:
        description: Recipient not found
    """
    data = request.get_json(force=True) or {}
    recipient_id = (data.get("recipient_id") or "").strip()
    amount = data.get("amount")
    notes = (data.get("notes") or "").strip()

    if not recipient_id or not amount:
        return jsonify({"error": MSG.REQUIRED_FIELD_MISSING}), 400
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return jsonify({"error": MSG.REQUIRED_FIELD_MISSING}), 400

    min_transfer = int(current_app.config.get("HP_TRANSFER_MIN_AMOUNT", 10))
    if amount < min_transfer:
        return jsonify({"error": resolve_msg(MSG.HP_TRANSFER_MIN, min=min_transfer)}), 400

    if recipient_id == g.user_id:
        return jsonify({"error": resolve_msg(MSG.HP_TRANSFER_SELF)}), 400

    db = get_db()

    # §Rule: sender must have completed at least hp_transfer_min_orders delivered orders.
    # min_orders is read from system_settings first (admin-editable), falling back to
    # the HP_TRANSFER_MIN_ORDERS config value (env-configurable), then hard default 3.
    min_orders_setting = db.table("system_settings").select("value").eq("key", "hp_transfer_min_orders").single().execute()
    _config_default = int(current_app.config.get("HP_TRANSFER_MIN_ORDERS", 3))
    min_orders = int((min_orders_setting or {}).get("value", _config_default) or _config_default)
    completed_orders = (
        db.table("orders")
        .select("id")
        .eq("user_id", g.user_id)
        .eq("status", "delivered")
        .execute()
    )
    # execute() returns a list on success, None / dict / empty on no-rows edge cases
    if isinstance(completed_orders, list):
        completed_count = len(completed_orders)
    elif isinstance(completed_orders, dict) and completed_orders.get("id"):
        completed_count = 1
    else:
        completed_count = 0
    if completed_count < min_orders:
        return jsonify({
            "error": resolve_msg(MSG.HP_TRANSFER_MIN_ORDERS, min_orders=min_orders, completed=completed_count),
            "min_orders_required": min_orders,
            "completed_orders": completed_count,
        }), 400

    recipient = db.table("profiles").select("id,full_name").eq("id", recipient_id).single().execute()
    if not recipient:
        return jsonify({"error": MSG.HP_TRANSFER_USER_NOT_FOUND}), 404

    sender = db.table("profiles").select("full_name").eq("id", g.user_id).single().execute()
    sender_name = (sender or {}).get("full_name", "Someone")
    recipient_name = recipient.get("full_name", "Someone")

    balance = get_hp_balance(g.user_id)
    if balance.get("active", 0) < amount:
        return jsonify({
            "error": resolve_msg(MSG.HP_TRANSFER_INSUFFICIENT, have=balance.get("active", 0), need=amount)
        }), 400

    transfer_note = notes or f"HP transfer from {sender_name}"
    spend_hp(g.user_id, amount, recipient_id, "hp_transfer", f"Sent {amount} HP to {recipient_name}")
    award_active_hp(
        user_id=recipient_id,
        amount=amount,
        source_type="hp_transfer",
        reference_id=g.user_id,
        reference_type="hp_transfer",
        notes=transfer_note,
    )

    # Notify the recipient that they received HP
    try:
        from app.services.notification_service import send_notification
        send_notification(
            user_id=recipient_id,
            notif_type="hp_transfer_recipient",
            template_data={"amount": amount, "sender": sender_name},
        )
    except Exception:
        pass

    return jsonify({
        "message": resolve_msg(MSG.HP_TRANSFER_OK),
        "amount": amount,
        "recipient_id": recipient_id,
        "recipient_name": recipient_name,
    }), 200


def _log_admin_action(actor_id, table, target_id, action, after_data=None):
    from app.db import get_db
    db = get_db()
    try:
        db.table("admin_audit_logs").insert({
            "actor_id": actor_id,
            "actor_role": "admin",
            "entity_type": table,
            "entity_id": target_id,
            "action": action,
            "after_value": after_data,
        })
    except Exception:
        pass
