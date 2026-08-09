"""
Notification Service — dispatches in-app, email, and push notifications.
All notification records written to the notifications table.
Throttling via notification_log (daily cap + 6-hour same-type gap for non-critical types).
Email and push dispatch via OneSignal (fire-and-forget, never raises).
"""

import os
import threading
import requests as http_requests
from datetime import datetime, timezone, timedelta
from app.db import get_db
from flask import current_app
from app.utils.logger import get_logger
from app.utils.retry import with_retry

logger = get_logger(__name__)


@with_retry(max_attempts=3, backoff=0.5)
def _onesignal_post(url: str, headers: dict, payload: dict) -> "http_requests.Response":
    return http_requests.post(url, headers=headers, json=payload, timeout=10)


_ONESIGNAL_BASE = os.environ.get("ONESIGNAL_BASE_URL", "https://api.onesignal.com")

# Critical notification types — operational / transactional: never throttled.
# Everything else is subject to the 6-hour same-type gap and daily cap.
_CRITICAL_NOTIF_TYPES = frozenset({
    "order_confirmed", "order_preparing", "order_ready", "order_assigned",
    "order_out_for_delivery", "order_delivered", "order_delivery_attempted",
    "order_cancelled", "order_refunded", "order_unclaimed",
    "hp_earned", "hp_unlocked", "hp_decay",
    "tier_upgrade", "tier_dropped", "tier_grace_period",
    "wallet_funded", "payment_confirmed",
    "referral_completed",
    "birthday_bonus", "graduation_hp", "hall_of_fame",
    "membership_anniversary", "order_lock_redeemed",
    "first_order_gift", "checkin_streak_week", "order_streak",
    "checkin_reclaimed", "hp_unlocked",
})


def _get_throttle_settings(db) -> tuple:
    """
    Read notification throttle settings from system_settings.
    Both values are admin-editable without a code deploy.

    Keys:
      notification_gap_minutes  — minimum minutes between same-type notifications
                                  per user (default 30)
      notification_daily_cap    — max non-critical notifications per user per day
                                  (default 20)

    Fails silently and returns safe defaults if the table is unreachable.
    """
    try:
        from flask import current_app
        gap_minutes = current_app.config.get("NOTIFICATION_GAP_MINUTES", 30)
        daily_cap = current_app.config.get("NOTIFICATION_DAILY_CAP", 20)
    except Exception:
        gap_minutes = int(os.environ.get("NOTIFICATION_GAP_MINUTES", 30))
        daily_cap = int(os.environ.get("NOTIFICATION_DAILY_CAP", 20))
    try:
        rows = (
            db.table("system_settings")
            .select("key,value")
            .in_("key", ["notification_gap_minutes", "notification_daily_cap"])
            .execute()
        ) or []
        for row in rows:
            k = row.get("key")
            v = row.get("value")
            if not v:
                continue
            if k == "notification_gap_minutes":
                gap_minutes = max(1, int(v))
            elif k == "notification_daily_cap":
                daily_cap = max(1, int(v))
    except Exception:
        pass
    return gap_minutes, daily_cap


def _is_throttled(db, user_id: str, notif_type: str) -> bool:
    """
    Returns True if the notification should be suppressed by throttle rules.
    Rules (applied only to non-critical types):
      1. Same-type gap: same type not sent to this user within notification_gap_minutes
         (admin-configurable via system_settings, default 30 min).
      2. Daily cap: total non-critical notifications logged today < notification_daily_cap
         (admin-configurable via system_settings, default 20).
    Fails open on any DB error (returns False so the notification is still sent).
    """
    if notif_type in _CRITICAL_NOTIF_TYPES:
        return False
    try:
        gap_minutes, daily_cap = _get_throttle_settings(db)
        now = datetime.now(timezone.utc)
        gap_ago = (now - timedelta(minutes=gap_minutes)).isoformat()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        # 1. Same-type gap
        recent = (
            db.table("notification_log")
            .select("id")
            .eq("user_id", user_id)
            .eq("type", notif_type)
            .gte("sent_at", gap_ago)
            .limit(1)
            .execute()
        )
        if recent:
            return True

        # 2. Daily cap
        today_count = (
            db.table("notification_log")
            .select("id")
            .eq("user_id", user_id)
            .gte("sent_at", today_start)
            .execute()
        )
        if len(today_count or []) >= daily_cap:
            return True

        return False
    except Exception:
        return False  # fail open — when in doubt, send


def _log_notification(db, user_id: str, notif_type: str) -> None:
    """Write one row to notification_log for throttle tracking. Never raises."""
    try:
        db.table("notification_log").insert({
            "user_id": user_id,
            "type": notif_type,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass


def get_notification_channels(notif_type: str, extra: list = None) -> list:
    """
    Return the canonical channel list for a given notification type.
    Rule: push + in_app always together. Email only for types in EMAIL_TYPES.
    extra: optional additional channels to merge in (e.g. ["email"]).

    EMAIL_TYPES (30) — updated per spec:
      - Removed: wallet_withdrawal_submitted/approved/rejected (withdrawals removed entirely)
      - Removed: order_lock_redeemed_discount/hp (in-app + push only)
      - Renamed: hp_transfer_received → hp_transfer_recipient
      - Renamed: hp_decay → hp_decay_applied
      - Renamed: tier_dropped → tier_downgrade
    """
    EMAIL_TYPES = {
        # Order (7)
        "order_confirmed", "order_delivered", "order_refunded",
        "order_cancelled", "order_cancelled_user", "order_cancelled_admin",
        "scheduled_order_cancelled",
        # Guest (1)
        "guest_order_claimed",
        # Wallet (2) — withdrawal types removed entirely
        "wallet_funded_card", "wallet_funded_bank",
        # HP (6)
        "hp_gift_received", "hp_transfer_recipient",
        "hp_decay_applied", "hp_decay_warning",
        "winback_95", "winback_118",
        # Tier (3)
        "tier_upgrade", "tier_grace_period", "tier_downgrade",
        # Account (8)
        "graduation_declared", "birthday_bonus",
        "password_changed", "password_reset", "email_verification",
        "account_deleted", "account_deactivated", "account_reactivated",
        # Events & Marketplace (3)
        "event_registered", "marketplace_purchase", "reward_fulfilled",
        # Squad (1)
        "squad_member_invite",
    }
    channels = ["push", "in_app"]
    if notif_type in EMAIL_TYPES or (extra and "email" in extra):
        channels = ["push", "in_app", "email"]
    return channels


def _fetch_user_name(user_id: str) -> str:
    """
    Look up a user's full_name from the profiles table.
    Returns the name string, or empty string on any failure.
    Never raises.
    """
    try:
        from app.utils.email import get_user_email_and_name
        _, name = get_user_email_and_name(user_id)
        return name or ""
    except Exception:
        return ""


def send_notification(
    user_id: str,
    notif_type: str,
    title: str = None,
    body: str = None,
    template_data: dict = None,
    reference_id: str = None,
    reference_type: str = None,
    action_url: str = None,
    channels: list = None,
    urgency: str = None,
    metadata: dict = None,
) -> list:
    """
    Write notification record(s) for each channel and dispatch externally.

    Two calling modes (backward-compatible):

    1. Legacy — caller supplies pre-rendered strings:
          send_notification(user_id, "order_confirmed",
                            title="Order Confirmed!", body="Your order #X …")

    2. Template — caller supplies raw data; service renders via registry:
          send_notification(user_id, "order_confirmed",
                            template_data={"order_id": "abc123", "name": "Ada"})

       When template_data is supplied:
         - The template is looked up in NOTIFICATION_TEMPLATES.
         - Critical fields missing → notification skipped, [] returned (RUN 4.3).
         - Non-critical fields missing → fallback values applied (RUN 4.2).
         - If include_name=True and "name" is absent from template_data,
           the user's full_name is fetched from the profiles table (RUN 3).
         - channels_override from the template takes effect unless channels
           is explicitly passed by the caller.

    channels: list of 'in_app' | 'email' | 'push'
              Default is ["push", "in_app"]; email added per EMAIL_TYPES.
    urgency:  None (normal) | "high" — high urgency sets max priority on push
              and is stored in metadata so the frontend surfaces it prominently.
    metadata: optional dict merged into the notification's metadata field.
    """
    from app.services.notification_templates import (
        render_notification_template,
        get_include_name,
    )

    # ── Template rendering mode (RUN 2, 3, 4) ────────────────────────────────
    if template_data is not None:
        # Inject user name if the type is personalized and name not supplied
        td = dict(template_data)
        if get_include_name(notif_type) and "name" not in td:
            fetched_name = _fetch_user_name(user_id)
            td["name"] = fetched_name if fetched_name else "there"

        rendered = render_notification_template(notif_type, td)

        if rendered is None:
            # Critical field missing or type unknown — skip send (RUN 4.3/4.4)
            logger.error(
                "send_notification: skipping %s for user %s — template render returned None",
                notif_type, user_id,
            )
            return []

        title, body, _include_name, channels_override = rendered

        # Apply template channel override only when caller didn't specify channels
        if channels is None and channels_override is not None:
            channels = channels_override

    # Guard: if neither mode supplied title/body, skip to avoid blank notifications
    if not title or not body:
        logger.error(
            "send_notification: skipping %s for user %s — title or body is empty",
            notif_type, user_id,
        )
        return []

    # Resolve {platform} and {currency} placeholders → APP_NAME / HP_CURRENCY_NAME from config
    try:
        _app_name = current_app.config.get("APP_NAME", os.environ.get("APP_NAME", "Holy Grills"))
        _currency = current_app.config.get("HP_CURRENCY_NAME", os.environ.get("HP_CURRENCY_NAME", "HP"))
    except RuntimeError:
        _app_name = os.environ.get("APP_NAME", "Holy Grills")
        _currency = os.environ.get("HP_CURRENCY_NAME", "HP")
    if "{platform}" in title:
        title = title.replace("{platform}", _app_name)
    if "{platform}" in body:
        body = body.replace("{platform}", _app_name)
    if "{currency}" in title:
        title = title.replace("{currency}", _currency)
    if "{currency}" in body:
        body = body.replace("{currency}", _currency)

    if channels is None:
        channels = ["push", "in_app"]

    db = get_db()

    # ── Throttle check (non-critical types only, fails open) ──────────────────
    if _is_throttled(db, user_id, notif_type):
        logger.debug(
            "send_notification: throttled %s to user %s (type=%s)",
            notif_type, user_id, notif_type,
        )
        return []

    records = []

    # Build merged metadata: internal fields + any caller-supplied extras
    merged_meta = {
        "reference_id": reference_id,
        "reference_type": reference_type,
        "urgency": urgency,
    }
    if metadata:
        merged_meta.update(metadata)

    for channel in channels:
        record = {
            "user_id": user_id,
            "type": notif_type,
            "channel": channel,
            "title": title,
            "body": body,
            "action_url": action_url,
            "metadata": merged_meta,
        }
        try:
            result = db.table("notifications").insert(record)
            saved = result[0] if isinstance(result, list) else result
            records.append(saved)

            if channel == "email":
                t = threading.Thread(
                    target=_dispatch_email_async,
                    args=(user_id, title, body, saved.get("id", "")),
                    daemon=True,
                )
                t.start()
            elif channel == "push":
                t = threading.Thread(
                    target=_dispatch_push_async,
                    args=(user_id, title, body, action_url, saved.get("id", ""), urgency),
                    daemon=True,
                )
                t.start()
        except Exception as e:
            logger.error("Error saving %s notification for %s: %s", channel, user_id, e)

    # Log to notification_log for throttle tracking (one entry per send call,
    # regardless of how many channels were used).
    if records:
        _log_notification(db, user_id, notif_type)

    return records


def send_blast(blast_id: str) -> dict:
    """
    Send a notification blast to a segment of users.

    Supported segment keys (all optional, combinable):
      tier               — tier slug: "ember"|"flame"|"blaze"|"holy"|"all"
      role               — "student"|"admin"|"kitchen"|"rider"|"all"
      department         — exact department name or "all"
      faculty            — faculty name or "all"
      has_pending_hp     — bool: True = has pending HP > 0
      hp_balance         — "low" (<100 HP) | "medium" (100–500) | "high" (>500)
      last_login_days    — int: users who logged in within last N days (or "any")
      last_order_days    — int: users who placed an order within last N days (or "any")
      total_orders       — "0"|"1-5"|"6-20"|"20+"
      has_referral       — bool: True = user has at least one referral
      has_squad_order    — bool: True = user has at least one squad order
      has_reviewed       — bool: True = user has left at least one review
      has_shared         — bool: True = user has at least one social share
      event_attendance   — "0"|"1-2"|"3+"
      has_graduated      — bool: True = user has graduated
      level_department   — "LEVEL:DEPT" e.g. "200:Computer Science"
      level              — academic level e.g. "200"

    Title/body may use {name} — it is substituted with the recipient's first name.
    """
    from datetime import timedelta

    db = get_db()
    blast = db.table("notification_blasts").select("*").eq("id", blast_id).single().execute()
    if not blast:
        raise ValueError("Blast not found")

    segment = blast.get("segment") or {}

    # ── Step 1: DB-level filters on profiles ────────────────────────────────
    profiles_q = (
        db.table("profiles")
        .select(
            "id,role,department,faculty,academic_level,"
            "hp_balance,last_seen_at,graduation_claimed,"
            "current_tier_id"
        )
        .eq("is_active", True)
    )

    if segment.get("role") and segment["role"] != "all":
        profiles_q = profiles_q.eq("role", segment["role"])

    if segment.get("department") and segment["department"] != "all":
        profiles_q = profiles_q.eq("department", segment["department"])

    if segment.get("faculty") and segment["faculty"] != "all":
        profiles_q = profiles_q.eq("faculty", segment["faculty"])

    if segment.get("level") and str(segment["level"]) != "all":
        profiles_q = profiles_q.eq("academic_level", str(segment["level"]))

    if segment.get("level_department") and segment["level_department"] != "all":
        try:
            _lvl, _dept = str(segment["level_department"]).split(":", 1)
            profiles_q = (
                profiles_q
                .eq("academic_level", _lvl.strip())
                .eq("department", _dept.strip())
            )
        except ValueError:
            pass

    # Tier filter: resolve slug to tier ID first
    if segment.get("tier") and segment["tier"] != "all":
        tier_row = (
            db.table("hp_tiers")
            .select("id")
            .eq("slug", segment["tier"].lower())
            .single()
            .execute()
        )
        if tier_row:
            profiles_q = profiles_q.eq("current_tier_id", tier_row["id"])

    profiles = profiles_q.execute() or []

    # ── Step 2: In-Python filters (require cross-table lookups) ─────────────
    user_ids: set = {p["id"] for p in profiles}

    def _shrink(keep_ids: set):
        """Intersect user_ids with keep_ids, rebuilding profiles list."""
        nonlocal profiles, user_ids
        user_ids &= keep_ids
        profiles = [p for p in profiles if p["id"] in user_ids]

    # HP balance bands
    hp_filter = segment.get("hp_balance")
    if hp_filter and hp_filter != "all":
        def _hp_ok(p):
            bal = int(p.get("hp_balance") or 0)
            if hp_filter == "low":    return bal < 100
            if hp_filter == "medium": return 100 <= bal <= 500
            if hp_filter == "high":   return bal > 500
            return True
        profiles = [p for p in profiles if _hp_ok(p)]
        user_ids = {p["id"] for p in profiles}

    # Pending HP — check monthly_hp_tracker for current month > 0
    if segment.get("has_pending_hp") is not None and user_ids:
        want = bool(segment["has_pending_hp"])
        current_month = datetime.now(timezone.utc).strftime("%Y-%m")
        tracker_rows = (
            db.table("monthly_hp_tracker")
            .select("user_id,total_earned")
            .in_("user_id", list(user_ids))
            .eq("month", current_month)
            .execute() or []
        )
        pending_uids = {r["user_id"] for r in tracker_rows if int(r.get("total_earned") or 0) > 0}
        _shrink(pending_uids if want else user_ids - pending_uids)

    # Has graduated — real column is graduation_claimed on profiles
    if segment.get("has_graduated") is not None:
        want = bool(segment["has_graduated"])
        profiles = [p for p in profiles if bool(p.get("graduation_claimed")) == want]
        user_ids = {p["id"] for p in profiles}

    # Last login window
    last_login_days = segment.get("last_login_days")
    if last_login_days and str(last_login_days) != "any" and user_ids:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(last_login_days))).isoformat()
        # Real column on profiles is last_seen_at (confirmed against live DB)
        profiles = [
            p for p in profiles
            if p.get("last_seen_at") and str(p["last_seen_at"]) >= cutoff
        ]
        user_ids = {p["id"] for p in profiles}

    # Last order window
    last_order_days = segment.get("last_order_days")
    if last_order_days and str(last_order_days) != "any" and user_ids:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=int(last_order_days))).isoformat()
        recent_uids = {
            r["user_id"]
            for r in (
                db.table("orders")
                .select("user_id")
                .in_("user_id", list(user_ids))
                .gte("created_at", cutoff)
                .execute() or []
            )
        }
        _shrink(recent_uids)

    # Total orders band
    total_orders_filter = segment.get("total_orders")
    if total_orders_filter and str(total_orders_filter) != "any" and user_ids:
        order_rows = (
            db.table("orders").select("user_id")
            .in_("user_id", list(user_ids))
            .execute() or []
        )
        counts: dict = {}
        for r in order_rows:
            uid = r["user_id"]
            counts[uid] = counts.get(uid, 0) + 1

        def _count_ok(uid):
            n = counts.get(uid, 0)
            if total_orders_filter == "0":    return n == 0
            if total_orders_filter == "1-5":  return 1 <= n <= 5
            if total_orders_filter == "6-20": return 6 <= n <= 20
            if total_orders_filter == "20+":  return n > 20
            return True

        _shrink({uid for uid in user_ids if _count_ok(uid)})

    # Has referral
    if segment.get("has_referral") is not None and user_ids:
        want = bool(segment["has_referral"])
        ref_uids = {
            r["referrer_id"]
            for r in (
                db.table("referrals").select("referrer_id")
                .in_("referrer_id", list(user_ids))
                .execute() or []
            )
        }
        _shrink(ref_uids if want else user_ids - ref_uids)

    # Has squad order — no squad_orders table; squad orders are in orders where is_squad_order=True
    # organizer = orders.user_id
    if segment.get("has_squad_order") is not None and user_ids:
        want = bool(segment["has_squad_order"])
        squad_uids = {
            r["user_id"]
            for r in (
                db.table("orders").select("user_id")
                .eq("is_squad_order", True)
                .in_("user_id", list(user_ids))
                .execute() or []
            )
        }
        _shrink(squad_uids if want else user_ids - squad_uids)

    # Has reviewed — real table is order_reviews (no reviews table in live DB)
    if segment.get("has_reviewed") is not None and user_ids:
        want = bool(segment["has_reviewed"])
        rev_uids = {
            r["user_id"]
            for r in (
                db.table("order_reviews").select("user_id")
                .in_("user_id", list(user_ids))
                .execute() or []
            )
        }
        _shrink(rev_uids if want else user_ids - rev_uids)

    # Has shared — real table is order_share_events (no social_shares table)
    if segment.get("has_shared") is not None and user_ids:
        want = bool(segment["has_shared"])
        share_uids = {
            r["user_id"]
            for r in (
                db.table("order_share_events").select("user_id")
                .in_("user_id", list(user_ids))
                .execute() or []
            )
        }
        _shrink(share_uids if want else user_ids - share_uids)

    # Event attendance band
    # event_checkins has no user_id — join through event_tickets (ticket_id → user_id)
    event_attendance = segment.get("event_attendance")
    if event_attendance and str(event_attendance) != "any" and user_ids:
        # Step A: get ticket_id → user_id for users in our set
        ticket_rows = (
            db.table("event_tickets").select("id,user_id")
            .in_("user_id", list(user_ids))
            .execute() or []
        )
        ticket_to_user = {r["id"]: r["user_id"] for r in ticket_rows}
        # Step B: count check-ins per user via ticket ownership
        checkin_rows = (
            db.table("event_checkins").select("ticket_id")
            .in_("ticket_id", list(ticket_to_user.keys()))
            .execute() or []
        ) if ticket_to_user else []
        att: dict = {}
        for r in checkin_rows:
            uid = ticket_to_user.get(r["ticket_id"])
            if uid:
                att[uid] = att.get(uid, 0) + 1

        def _att_ok(uid):
            n = att.get(uid, 0)
            if event_attendance == "0":   return n == 0
            if event_attendance == "1-2": return 1 <= n <= 2
            if event_attendance == "3+":  return n >= 3
            return True

        _shrink({uid for uid in user_ids if _att_ok(uid)})

    # ── Step 3: Send — personalise {name} if present in title/body ──────────
    channels = blast.get("channels", ["in_app"])
    title_tpl = blast.get("title", "")
    body_tpl = blast.get("body", "")
    has_name = "{name}" in title_tpl or "{name}" in body_tpl
    count = 0

    for uid in user_ids:
        notif_title = title_tpl
        notif_body = body_tpl
        if has_name:
            full_name = _fetch_user_name(uid)
            first = (full_name or "").split()[0] if full_name else "there"
            notif_title = title_tpl.replace("{name}", first)
            notif_body = body_tpl.replace("{name}", first)
        send_notification(
            user_id=uid,
            notif_type="blast",
            title=notif_title,
            body=notif_body,
            channels=channels,
        )
        count += 1

    db.table("notification_blasts").eq("id", blast_id).update({"status": "sent"})
    return {"sent_to": count}


def mark_read(notification_id: str, user_id: str) -> dict:
    db = get_db()
    updated = (
        db.table("notifications")
        .eq("id", notification_id)
        .eq("user_id", user_id)
        .update({"read_at": datetime.now(timezone.utc).isoformat()})
    )
    return updated[0] if isinstance(updated, list) else updated


# ─────────────────────────────────────────────────────────────────────────────
# External dispatch helpers — fire-and-forget, never raise
# ─────────────────────────────────────────────────────────────────────────────

def _get_onesignal_creds() -> tuple:
    """Return (app_id, api_key) from env. Returns ('','') if not configured."""
    app_id = os.environ.get("ONESIGNAL_APP_ID", "")
    api_key = os.environ.get("ONESIGNAL_API_KEY", "")
    return app_id, api_key


def _dispatch_email_async(user_id: str, subject: str, body: str, notification_id: str):
    """
    Send a transactional email via Resend to the user's registered email address.
    Looks up user email from profiles. Silently skips if credentials or email not found.
    """
    try:
        api_key = os.environ.get("RESEND_API_KEY", "")
        if not api_key:
            return

        from app.utils.email import get_user_email_and_name, send_email_raw, _build_html
        email, name = get_user_email_and_name(user_id)
        if not email:
            return

        app_tagline = os.environ.get("APP_TAGLINE", "Holy Grills FUTA")
        html_body = _build_html(name or "there", body, app_tagline)
        send_email_raw(email, name or "there", subject, html_body)
    except Exception as e:
        logger.error("Email dispatch error for user %s: %s", user_id, e)


def _dispatch_push_async(user_id: str, title: str, body: str, action_url: str, notification_id: str, urgency: str = None):
    """
    Send a push notification via OneSignal using user_id as external_id.
    Requires user to have a registered push subscription with their user_id as external_id.
    Silently skips if credentials not configured or user not subscribed.
    urgency="high" sets maximum delivery priority on Android (priority: 10) and
    time-sensitive interruption level on iOS so the notification breaks through
    Focus/DND modes.
    """
    try:
        app_id, api_key = _get_onesignal_creds()
        if not app_id or not api_key:
            return

        payload = {
            "app_id": app_id,
            "include_aliases": {"external_id": [user_id]},
            "target_channel": "push",
            "headings": {"en": title},
            "contents": {"en": body},
        }
        if action_url:
            payload["url"] = action_url
        if urgency == "high":
            payload["priority"] = 10                          # Android: max priority
            payload["ios_interruption_level"] = "time-sensitive"  # iOS 15+: breaks Focus

        resp = _onesignal_post(
            f"{_ONESIGNAL_BASE}/notifications",
            headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
            payload=payload,
        )
        if resp.status_code not in (200, 202):
            logger.warning("OneSignal push error %s for user %s: %s", resp.status_code, user_id, resp.text[:200])
    except Exception as e:
        logger.error("Push dispatch error for user %s: %s", user_id, e)
