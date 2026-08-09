"""
app/services/notification_templates.py — Notification Template Registry

Maps every notification type key to:
  - title / body   : template strings sourced exclusively from MSG
  - include_name   : True → fetch user's name and inject {name} if not supplied
  - channels       : None (use get_notification_channels logic) or explicit override

Rendering pipeline (render_notification_template):
  1. Look up the template.  Type not in registry → return None (caller supplies title/body).
  2. Collect every {placeholder} key in title + body.
  3. Critical placeholders missing from template_data → log and return None (skip send).
  4. Non-critical placeholders missing → substitute from NON_CRITICAL_FALLBACKS.
  5. Format strings and return (title, body, include_name, channels_override).

Critical vs non-critical definition matches the spec in RUN 4.
"""

import os
import re
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── Non-critical fallbacks ─────────────────────────────────────────────────────
# Missing non-critical placeholder → use this value instead of skipping.
NON_CRITICAL_FALLBACKS: dict = {
    # Spec-defined non-critical fields
    "name":           "there",
    "tier_name":      "your tier",
    "streak_count":   "your streak",
    "gift_sender":    "someone",
    "batch_id":       "your batch",
    "platform":       "social media",
    "currency":       os.environ.get("HP_CURRENCY_NAME", "HP"),
    "referral_count": "your referrals",
    # Additional MSG-placeholder non-critical fallbacks
    "from_tier":      "your previous tier",
    "to_tier":        "your new tier",
    "months":         "your",
    "period":         "recent",
    "multiplier":     "bonus",
    "days":           "a few",
    "status":         "updated",
    "plural":         "s",
    "week":           "current",
    "weeks":          "a few",
    "saved":          "0",
    "organizer":      "A member",
    "date":           "the scheduled date",
    "reason":         "",
    "sender":         "someone",
    "vendor_name":    "A vendor",
    "service_title":  "a listing",
    "event_name":     "the event",
    "event_type":     "Unknown event",
    "reference":      "N/A",
    "error":          "Unknown error",
    "remaining":      "limited",
    "hp_earned":      "0",
    "rank":           "your",
    "grace_days":     "7",
    "total_hp":       "some",   # used in HP_EARNED_TITLE as {total_hp}
    "level":          "your",   # used in GRADUATION_BONUS_BODY as {level}
}

# ── Critical fields ────────────────────────────────────────────────────────────
# Any of these missing from template_data → skip the notification entirely.
# Includes both spec-defined semantic names AND the actual MSG placeholder names
# that differ (e.g. templates use {pct} while the spec calls it discount_pct).
CRITICAL_FIELDS: frozenset = frozenset({
    # Spec-defined critical fields
    "order_id",
    "order_ref",
    "hp_amount",
    "hp",
    "amount",
    "code",
    "event_title",
    "reward_name",
    "discount_pct",
    "lock_date",
    # Actual MSG placeholder names that map to critical spec fields
    "pct",          # MSG templates use {pct} for discount percentage
    "unlocked_hp",  # MSG uses {unlocked_hp} in HP_UNLOCKED_TITLE/BODY
    "title",        # MSG uses {title} in EVENT_REGISTERED_TITLE, MARKETPLACE_PURCHASE_BODY
})

# ── Placeholder extraction ─────────────────────────────────────────────────────
# Matches simple {word} and format-spec variants like {amount:.0f}, {pct:.0f}
_PLACEHOLDER_RE = re.compile(r"\{(\w+)(?:[^}]*)?\}")


def _placeholders(s: str) -> set:
    """Return the set of placeholder key names found in a template string."""
    return set(_PLACEHOLDER_RE.findall(s))


# ── Non-personalized type set ──────────────────────────────────────────────────
# Notification types where include_name is False by default.
# Any type NOT in this set is considered personalized (include_name=True).
_NON_PERSONALIZED_TYPES: frozenset = frozenset({
    # Legacy admin-prefixed types
    "welcome_email",
    "email_verification",
    "password_reset",
    "admin_new_user",
    "admin_new_order",
    "admin_order_attention",
    "admin_bulk_hp",
    "admin_cron_failed",
    "admin_setting_updated",
    "admin_low_inventory",
    "admin_webhook_failure",
    "admin_audit_log",
    "admin_catering_request",
    "admin_vendor_request",
    "system_announcement",
    "blast",                  # Admin-authored blasts — no automatic name injection
    "squad_member_invite",    # Invite has sender's name; not the recipient's
    # New operational / admin types (registered above)
    "gift_granted",           # kitchen/admin alert
    "catering_request",       # admin catering alert
    "marketplace_request",    # admin marketplace alert
    "low_inventory",          # admin inventory alert
    "webhook_failure",        # admin webhook failure alert
    "birthday_report",        # admin birthday digest
    "new_reward",             # broadcast — {name} = reward name, not user's
    "reward_status",          # {name} = reward name, not user's
})


# ── Template registry ──────────────────────────────────────────────────────────
# Keys: notification type strings used across the codebase.
# Values:
#   title        — MSG constant (template string, may contain {placeholders})
#   body         — MSG constant (template string, may contain {placeholders})
#   include_name — whether to fetch + inject {name} when absent from template_data
#   channels     — None = derive from EMAIL_TYPES in notification_service;
#                  list  = hard override (e.g. in_app+push only, no email)
NOTIFICATION_TEMPLATES: dict = {

    # ── Auth / Account ─────────────────────────────────────────────────────────
    "password_changed": {
        "title":        MSG.NOTIF_PASSWORD_CHANGED_TITLE,
        "body":         MSG.NOTIF_PASSWORD_CHANGED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "account_deactivated": {
        "title":        MSG.NOTIF_ACCOUNT_DEACTIVATED_TITLE,
        "body":         MSG.NOTIF_ACCOUNT_DEACTIVATED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "account_reactivated": {
        "title":        MSG.NOTIF_ACCOUNT_REACTIVATED_TITLE,
        "body":         MSG.NOTIF_ACCOUNT_REACTIVATED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "account_deleted": {
        "title":        MSG.NOTIF_ACCOUNT_DELETED_TITLE,
        "body":         MSG.NOTIF_ACCOUNT_DELETED_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Non-personalized: Auth/Security ───────────────────────────────────────
    "welcome_email": {
        "title":        MSG.NOTIF_WELCOME_TITLE,
        "body":         MSG.NOTIF_WELCOME_BODY,
        "include_name": False,
        "channels":     None,
    },
    "email_verification": {
        "title":        MSG.NOTIF_EMAIL_VERIFY_TITLE,
        "body":         MSG.NOTIF_EMAIL_VERIFY_BODY,
        "include_name": False,
        "channels":     None,
    },
    "password_reset": {
        "title":        MSG.NOTIF_PASSWORD_RESET_TITLE,
        "body":         MSG.NOTIF_PASSWORD_RESET_BODY,
        "include_name": False,
        "channels":     None,
    },

    # ── Login Streak ───────────────────────────────────────────────────────────
    "login_streak": {
        "title":        MSG.LOGIN_STREAK_TITLE,
        "body":         MSG.LOGIN_STREAK_BODY,
        "include_name": True,
        "channels":     None,
    },
    "login_streak_checkin": {
        "title":        MSG.NOTIF_LOGIN_STREAK_CHECKIN_TITLE,
        "body":         MSG.NOTIF_LOGIN_STREAK_CHECKIN_BODY,
        "include_name": True,
        "channels":     None,
    },
    "login_streak_bonus": {
        "title":        MSG.LOGIN_STREAK_WEEK_COMPLETE_TITLE,
        "body":         MSG.LOGIN_STREAK_WEEK_COMPLETE_BODY,
        "include_name": True,
        "channels":     None,
    },
    "checkin_streak_week": {
        "title":        MSG.LOGIN_STREAK_WEEK_COMPLETE_TITLE,
        "body":         MSG.LOGIN_STREAK_WEEK_COMPLETE_BODY,
        "include_name": True,
        "channels":     None,
    },
    "login_streak_cycle_failed": {
        "title":        MSG.NOTIF_LOGIN_STREAK_CYCLE_FAILED_TITLE,
        "body":         MSG.NOTIF_LOGIN_STREAK_CYCLE_FAILED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "login_streak_reclaim": {
        "title":        MSG.NOTIF_LOGIN_STREAK_RECLAIM_TITLE,
        "body":         MSG.NOTIF_LOGIN_STREAK_RECLAIM_BODY,
        "include_name": True,
        "channels":     None,
    },
    "checkin_reclaimed": {
        "title":        MSG.LOGIN_STREAK_RECLAIM_TITLE,
        "body":         MSG.LOGIN_STREAK_RECLAIM_BODY_ORDER,
        "include_name": True,
        "channels":     None,
    },

    # ── Orders ─────────────────────────────────────────────────────────────────
    "order_confirmed": {
        "title":        MSG.ORDER_CONFIRMED_TITLE,
        "body":         MSG.ORDER_CONFIRMED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_preparing": {
        "title":        MSG.ORDER_PREPARING_TITLE,
        "body":         MSG.ORDER_PREPARING_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_ready": {
        "title":        MSG.ORDER_READY_TITLE,
        "body":         MSG.ORDER_READY_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_assigned": {
        "title":        MSG.ORDER_ASSIGNED_TITLE,
        "body":         MSG.ORDER_ASSIGNED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_out_for_delivery": {
        "title":        MSG.ORDER_OUT_FOR_DELIVERY_TITLE,
        "body":         MSG.ORDER_OUT_FOR_DELIVERY_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_delivered": {
        "title":        MSG.ORDER_DELIVERED_TITLE,
        "body":         MSG.ORDER_DELIVERED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_delivery_attempted": {
        "title":        MSG.ORDER_DELIVERY_ATTEMPTED_TITLE,
        "body":         MSG.ORDER_DELIVERY_ATTEMPTED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_unclaimed": {
        "title":        MSG.ORDER_UNCLAIMED_TITLE,
        "body":         MSG.ORDER_UNCLAIMED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_cancelled": {
        "title":        MSG.ORDER_CANCELLED_TITLE,
        "body":         MSG.ORDER_CANCELLED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_cancelled_user": {
        "title":        MSG.ORDER_CANCELLED_TITLE,
        "body":         MSG.ORDER_CANCELLED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_cancelled_admin": {
        "title":        MSG.ORDER_CANCELLED_TITLE,
        "body":         MSG.ORDER_CANCELLED_BODY,
        "include_name": False,
        "channels":     None,
    },
    "order_refunded": {
        "title":        MSG.ORDER_REFUND_TITLE,
        "body":         MSG.ORDER_REFUND_BODY_WALLET,
        "include_name": True,
        "channels":     None,
    },
    "scheduled_order_promoted": {
        "title":        MSG.SCHEDULED_ORDER_PROMOTED_TITLE,
        "body":         MSG.SCHEDULED_ORDER_PROMOTED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "scheduled_order_cancelled": {
        "title":        MSG.SCHEDULED_ORDER_CANCELLED_TITLE,
        "body":         MSG.SCHEDULED_ORDER_CANCELLED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "scheduled_order_due": {
        "title":        MSG.SCHEDULED_ORDER_DUE_TITLE,
        "body":         MSG.SCHEDULED_ORDER_DUE_BODY,
        "include_name": True,
        "channels":     None,
    },
    "guest_order_claimed": {
        "title":        MSG.GUEST_ORDER_CLAIMED_TITLE,
        "body":         MSG.GUEST_ORDER_CLAIMED_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Squad ──────────────────────────────────────────────────────────────────
    "squad_member_added": {
        "title":        MSG.NOTIF_SQUAD_MEMBER_ADDED_TITLE,
        "body":         MSG.SQUAD_ORDER_ADDED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "squad_hp_split": {
        "title":        MSG.SQUAD_HP_SPLIT_TITLE,
        "body":         MSG.SQUAD_HP_SPLIT_BODY,
        "include_name": True,
        "channels":     None,
    },
    "squad_order_ready": {
        "title":        MSG.SQUAD_ORDER_READY_TITLE,
        "body":         MSG.SQUAD_ORDER_READY_BODY,
        "include_name": True,
        "channels":     None,
    },
    "squad_member_invite": {
        "title":        MSG.NOTIF_SQUAD_INVITE_TITLE,
        "body":         MSG.NOTIF_SQUAD_INVITE_BODY,
        "include_name": False,   # invite body already references organiser, not recipient name
        "channels":     None,
    },

    # ── Order Locks ────────────────────────────────────────────────────────────
    "order_lock_created": {
        "title":        MSG.ORDER_LOCK_CREATED,
        "body":         MSG.ORDER_LOCK_REMINDER_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_lock_reminder": {
        "title":        MSG.ORDER_LOCK_REMINDER_TITLE,
        "body":         MSG.ORDER_LOCK_REMINDER_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_lock_reminder_hp": {
        "title":        MSG.ORDER_LOCK_REMINDER_TITLE,
        "body":         MSG.ORDER_LOCK_REMINDER_BODY_HP,
        "include_name": True,
        "channels":     None,
    },
    "order_lock_redeemed_discount": {
        "title":        MSG.ORDER_LOCK_REDEEMED_TITLE,
        "body":         MSG.ORDER_LOCK_REDEEMED_BODY,
        "include_name": True,
        "channels":     ["push", "in_app"],   # No email — per spec
    },
    "order_lock_redeemed_hp": {
        "title":        MSG.ORDER_LOCK_REDEEMED_HP_TITLE,
        "body":         MSG.ORDER_LOCK_REDEEMED_HP_BODY,
        "include_name": True,
        "channels":     ["push", "in_app"],   # No email — per spec
    },
    "order_lock_expired": {
        "title":        MSG.ORDER_LOCK_EXPIRY_TITLE,
        "body":         MSG.ORDER_LOCK_EXPIRY_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Reviews ────────────────────────────────────────────────────────────────
    "review_request": {
        "title":        MSG.REVIEW_REQUEST_TITLE,
        "body":         MSG.REVIEW_REQUEST_BODY,
        "include_name": True,
        "channels":     None,
    },
    "review_submitted": {
        "title":        MSG.REVIEW_SUBMITTED_TITLE,
        "body":         MSG.REVIEW_SUBMITTED_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Shares ─────────────────────────────────────────────────────────────────
    "share_prompt": {
        "title":        MSG.SHARE_PROMPT_HP_TITLE,
        "body":         MSG.SHARE_PROMPT_HP_BODY,
        "include_name": True,
        "channels":     None,
    },
    "share_completed": {
        "title":        MSG.SHARE_COMPLETED_TITLE,
        "body":         MSG.SHARE_COMPLETED_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── HP Earned ──────────────────────────────────────────────────────────────
    "hp_earned": {
        "title":        MSG.HP_EARNED_TITLE,
        "body":         MSG.HP_EARNED_FOOD_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_earned_welcome": {
        "title":        MSG.HP_EARNED_WELCOME_TITLE,
        "body":         MSG.HP_EARNED_WELCOME_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_earned_review": {
        "title":        MSG.HP_EARNED_TITLE,
        "body":         MSG.HP_EARNED_FOOD_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_earned_share": {
        "title":        MSG.SHARE_PROMPT_HP_TITLE,
        "body":         MSG.SHARE_PROMPT_HP_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_earned_topup": {
        "title":        MSG.HP_EARNED_TOPUP_TITLE,
        "body":         MSG.HP_EARNED_TOPUP_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_earned_event": {
        "title":        MSG.EVENT_HP_PENDING_TITLE,
        "body":         MSG.EVENT_HP_PENDING_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_earned_challenge": {
        "title":        MSG.HP_EARNED_TITLE,
        "body":         MSG.HP_EARNED_CHALLENGE_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_earned_social": {
        "title":        MSG.HP_EARNED_SOCIAL_TITLE,
        "body":         MSG.HP_EARNED_SOCIAL_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_earned_login_streak": {
        "title":        MSG.HP_EARNED_TITLE,
        "body":         MSG.HP_EARNED_LOGIN_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_earned_order_streak": {
        "title":        MSG.ORDER_STREAK_TITLE,
        "body":         MSG.ORDER_STREAK_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_earned_anniversary": {
        "title":        MSG.ANNIVERSARY_TITLE,
        "body":         MSG.HP_EARNED_ANNIVERSARY_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_earned_graduation": {
        "title":        MSG.GRADUATION_BONUS_TITLE,
        "body":         MSG.GRADUATION_BONUS_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_unlocked": {
        "title":        MSG.HP_UNLOCKED_TITLE,
        "body":         MSG.HP_UNLOCKED_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Referrals ──────────────────────────────────────────────────────────────
    "referral_hp_earned": {
        "title":        MSG.REFERRAL_HP_EARNED_TITLE,
        "body":         MSG.REFERRAL_HP_EARNED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "referral_signup": {
        "title":        MSG.REFERRAL_SIGNUP_TITLE,
        "body":         MSG.REFERRAL_SIGNUP_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Birthday ───────────────────────────────────────────────────────────────
    "birthday_bonus": {
        "title":        MSG.BIRTHDAY_TITLE,
        "body":         MSG.BIRTHDAY_BODY,
        "include_name": True,
        "channels":     None,
    },
    "birthday_blast": {
        "title":        MSG.BIRTHDAY_BLAST_TITLE,
        "body":         MSG.BIRTHDAY_BLAST_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── HP Gift ────────────────────────────────────────────────────────────────
    "hp_gift_received": {
        "title":        MSG.HP_GIFT_RECEIVED_TITLE,
        "body":         MSG.HP_GIFT_RECEIVED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_gift_sent": {
        "title":        MSG.HP_GIFT_SENT_TITLE,
        "body":         MSG.HP_GIFT_SENT_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── HP Transfer ────────────────────────────────────────────────────────────
    "hp_transfer_sent": {
        "title":        MSG.HP_TRANSFER_OK,
        "body":         MSG.HP_TRANSFER_OK,
        "include_name": True,
        "channels":     None,
    },
    # Canonical name per spec; hp.py call site uses this type
    "hp_transfer_recipient": {
        "title":        MSG.HP_TRANSFER_RECEIVED_TITLE,
        "body":         MSG.HP_TRANSFER_RECEIVED_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Rewards ────────────────────────────────────────────────────────────────
    "reward_redeemed": {
        "title":        MSG.REWARD_REDEEMED_TITLE,
        "body":         MSG.REWARD_REDEEMED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "reward_fulfilled": {
        "title":        MSG.REWARD_FULFILLED_TITLE,
        "body":         MSG.REWARD_STATUS_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Flash Sale ─────────────────────────────────────────────────────────────
    "flash_sale_redeemed": {
        "title":        MSG.FLASH_REDEEMED_TITLE,
        "body":         MSG.FLASH_REDEEMED_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── HP Decay / Win-Back ────────────────────────────────────────────────────
    "hp_decay_warning": {
        "title":        MSG.HP_DECAY_WARNING_TITLE,
        "body":         MSG.HP_DECAY_WARNING_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hp_decay_applied": {
        "title":        MSG.HP_DECAY_TITLE,
        "body":         MSG.HP_DECAY_BODY,
        "include_name": True,
        "channels":     None,
    },
    "winback_70": {
        "title":        MSG.WINBACK_DAY70_TITLE,
        "body":         MSG.WINBACK_DAY70_BODY,
        "include_name": True,
        "channels":     None,
    },
    "winback_95": {
        "title":        MSG.WINBACK_DAY95_TITLE,
        "body":         MSG.WINBACK_DAY95_BODY,
        "include_name": True,
        "channels":     None,
    },
    "winback_118": {
        "title":        MSG.WINBACK_DAY118_TITLE,
        "body":         MSG.WINBACK_DAY118_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Tiers ──────────────────────────────────────────────────────────────────
    "tier_upgrade": {
        "title":        MSG.TIER_UPGRADE_TITLE,
        "body":         MSG.TIER_UPGRADE_BODY,
        "include_name": True,
        "channels":     None,
    },
    "tier_grace_period": {
        "title":        MSG.TIER_GRACE_TITLE,
        "body":         MSG.TIER_GRACE_BODY,
        "include_name": True,
        "channels":     None,
    },
    "tier_grace_ended": {
        "title":        MSG.TIER_GRACE_ENDED_TITLE,
        "body":         MSG.TIER_GRACE_ENDED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "tier_downgrade": {
        "title":        MSG.TIER_DROPPED_TITLE,
        "body":         MSG.TIER_DROPPED_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Events ─────────────────────────────────────────────────────────────────
    "event_registered": {
        "title":        MSG.EVENT_REGISTERED_TITLE,
        "body":         MSG.EVENT_REGISTERED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "event_checkin": {
        "title":        MSG.EVENT_HP_PENDING_TITLE,
        "body":         MSG.EVENT_HP_PENDING_BODY,
        "include_name": True,
        "channels":     None,
    },
    "event_ticket_purchased": {
        "title":        MSG.EVENT_TICKET_PURCHASED_TITLE,
        "body":         MSG.EVENT_TICKET_PURCHASED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "event_catering_submitted": {
        "title":        MSG.EVENT_CATERING_SUBMITTED_TITLE,
        "body":         MSG.EVENT_CATERING_SUBMITTED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "event_catering_status": {
        "title":        MSG.EVENT_CATERING_STATUS_TITLE,
        "body":         MSG.EVENT_CATERING_STATUS_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Marketplace ────────────────────────────────────────────────────────────
    "marketplace_purchase": {
        "title":        MSG.MARKETPLACE_PURCHASE_TITLE,
        "body":         MSG.MARKETPLACE_PURCHASE_BODY,
        "include_name": True,
        "channels":     None,
    },
    "marketplace_access_code": {
        "title":        MSG.MARKETPLACE_ACCESS_CODE_TITLE,
        "body":         MSG.MARKETPLACE_ACCESS_CODE_BODY,
        "include_name": True,
        "channels":     None,
    },
    "marketplace_escrow": {
        "title":        MSG.MARKETPLACE_ESCROW_TITLE,
        "body":         MSG.MARKETPLACE_ESCROW_BODY,
        "include_name": True,
        "channels":     None,
    },
    "vendor_request_submitted": {
        "title":        MSG.VENDOR_REQUEST_SUBMITTED_TITLE,
        "body":         MSG.VENDOR_REQUEST_SUBMITTED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "vendor_request_approved": {
        "title":        MSG.VENDOR_REQUEST_APPROVED_TITLE,
        "body":         MSG.VENDOR_REQUEST_APPROVED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "vendor_request_rejected": {
        "title":        MSG.VENDOR_REQUEST_REJECTED_TITLE,
        "body":         MSG.VENDOR_REQUEST_REJECTED_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Wallet ─────────────────────────────────────────────────────────────────
    "wallet_funded_card": {
        "title":        MSG.WALLET_FUNDED_CARD_TITLE,
        "body":         MSG.WALLET_FUNDED_CARD_BODY,
        "include_name": True,
        "channels":     None,
    },
    "wallet_funded_bank": {
        "title":        MSG.WALLET_FUNDED_BANK_TITLE,
        "body":         MSG.WALLET_FUNDED_BANK_BODY,
        "include_name": True,
        "channels":     None,
    },
    "wallet_funded": {
        "title":        MSG.WALLET_FUNDED_TITLE,
        "body":         MSG.WALLET_FUNDED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "wallet_balance_low": {
        "title":        MSG.WALLET_LOW_TITLE,
        "body":         MSG.WALLET_LOW_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Rider ──────────────────────────────────────────────────────────────────
    "rider_batch_assigned": {
        "title":        MSG.RIDER_BATCH_TITLE,
        "body":         MSG.RIDER_BATCH_BODY,
        "include_name": True,
        "channels":     None,
    },
    "rider_order_ready": {
        "title":        MSG.RIDER_ORDER_READY_TITLE,
        "body":         MSG.RIDER_ORDER_READY_BODY,
        "include_name": True,
        "channels":     None,
    },
    "rider_pickup_confirmed": {
        "title":        MSG.RIDER_PICKUP_CONFIRMED_TITLE,
        "body":         MSG.RIDER_PICKUP_CONFIRMED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "rider_delivery_confirmed": {
        "title":        MSG.RIDER_DELIVERY_CONFIRMED_TITLE,
        "body":         MSG.RIDER_DELIVERY_CONFIRMED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "rider_delivery_attempted": {
        "title":        MSG.RIDER_DELIVERY_ATTEMPTED_TITLE,
        "body":         MSG.RIDER_DELIVERY_ATTEMPTED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "rider_earnings": {
        "title":        MSG.RIDER_EARNINGS_TITLE,
        "body":         MSG.RIDER_EARNINGS_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Kitchen / operational ──────────────────────────────────────────────────
    "kitchen_order_received": {
        "title":        MSG.KITCHEN_ORDER_TITLE,
        "body":         MSG.KITCHEN_ORDER_BODY,
        "include_name": True,
        "channels":     None,
    },
    "kitchen_batch_ready": {
        "title":        MSG.KITCHEN_BATCH_TITLE,
        "body":         MSG.KITCHEN_BATCH_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Leaderboard ────────────────────────────────────────────────────────────
    "leaderboard_rank": {
        "title":        MSG.LEADERBOARD_RANK_TITLE,
        "body":         MSG.LEADERBOARD_RANK_BODY,
        "include_name": True,
        "channels":     None,
    },
    "leaderboard_top10": {
        "title":        MSG.LEADERBOARD_RANK_TITLE,
        "body":         MSG.LEADERBOARD_RANK_BODY,
        "include_name": True,
        "channels":     None,
    },
    "leaderboard_top4": {
        "title":        MSG.LEADERBOARD_TOP4_TITLE,
        "body":         MSG.LEADERBOARD_TOP4_BODY,
        "include_name": True,
        "channels":     None,
    },
    "squad_leaderboard_rank": {
        "title":        MSG.SQUAD_LEADERBOARD_TITLE,
        "body":         MSG.SQUAD_LEADERBOARD_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hall_of_fame": {
        "title":        MSG.HALL_OF_FAME_TITLE,
        "body":         MSG.HALL_OF_FAME_BODY,
        "include_name": True,
        "channels":     None,
    },
    "hall_of_fame_card": {
        "title":        MSG.HALL_OF_FAME_CARD_TITLE,
        "body":         MSG.HALL_OF_FAME_CARD_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Phase 3 — Leaderboard Prize ───────────────────────────────────────────
    "leaderboard_prize": {
        "title":        MSG.LEADERBOARD_PRIZE_TITLE,
        "body":         MSG.LEADERBOARD_PRIZE_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Phase 3 — Exclusive Spin Win ──────────────────────────────────────────
    "exclusive_spin_won": {
        "title":        MSG.EXCLUSIVE_SPIN_WON_TITLE,
        "body":         MSG.EXCLUSIVE_SPIN_WON_BODY,
        "include_name": True,
        "channels":     ["push", "in_app"],   # Prize is shown inline — no email needed
    },

    # ── Phase 3 — Daily Check-in HP ──────────────────────────────────────────
    "daily_checkin": {
        "title":        MSG.DAILY_CHECKIN_TITLE,
        "body":         MSG.DAILY_CHECKIN_BODY,
        "include_name": True,
        "channels":     ["push", "in_app"],   # Lightweight — no email
    },

    # ── Phase 3 — Admin: New HoF Induction Alert ─────────────────────────────
    "admin_hof_induction": {
        "title":        MSG.ADMIN_HOF_INDUCTION_TITLE,
        "body":         MSG.ADMIN_HOF_INDUCTION_BODY,
        "include_name": False,   # Admin notification — no name prefix needed
        "channels":     ["push", "in_app"],
    },

    # ── Order Streak ───────────────────────────────────────────────────────────
    "order_streak": {
        "title":        MSG.ORDER_STREAK_TITLE,
        "body":         MSG.ORDER_STREAK_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_streak_update": {
        "title":        MSG.ORDER_STREAK_TITLE,
        "body":         MSG.ORDER_STREAK_BODY,
        "include_name": True,
        "channels":     None,
    },
    "order_streak_broken": {
        "title":        MSG.ORDER_STREAK_BROKEN_TITLE,
        "body":         MSG.ORDER_STREAK_BROKEN_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Abandoned Cart ─────────────────────────────────────────────────────────
    "abandoned_cart": {
        "title":        MSG.ABANDONED_CART_TITLE,
        "body":         MSG.ABANDONED_CART_BODY,
        "include_name": True,
        "channels":     None,
    },
    "abandoned_cart_nudge": {
        "title":        MSG.ADMIN_NUDGE_TITLE,
        "body":         MSG.ADMIN_NUDGE_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Membership Anniversary ─────────────────────────────────────────────────
    "membership_anniversary": {
        "title":        MSG.ANNIVERSARY_TITLE,
        "body":         MSG.ANNIVERSARY_BODY,
        "include_name": True,
        "channels":     None,
    },
    # ── Graduation ─────────────────────────────────────────────────────────────
    "graduation_declared": {
        "title":        MSG.GRADUATION_DECLARED_TITLE,
        "body":         MSG.GRADUATION_DECLARED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "graduation_hp": {
        "title":        MSG.GRADUATION_BONUS_TITLE,
        "body":         MSG.GRADUATION_BONUS_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Scheduled Content (now personalized) ───────────────────────────────────
    "daily_greeting": {
        "title":        MSG.DAILY_GREETING_TITLE,
        "body":         MSG.DAILY_GREETING_BODY,
        "include_name": True,
        "channels":     None,
    },
    "weekly_prayer": {
        "title":        MSG.WEEKLY_PRAYER_TITLE,
        "body":         MSG.WEEKLY_PRAYER_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Multiplier Events ──────────────────────────────────────────────────────
    "multiplier_live": {
        "title":        MSG.MULTIPLIER_LIVE_TITLE,
        "body":         MSG.MULTIPLIER_LIVE_BODY,
        "include_name": True,
        "channels":     None,
    },
    "multiplier_expires": {
        "title":        MSG.MULTIPLIER_EXPIRES_TITLE,
        "body":         MSG.MULTIPLIER_EXPIRES_BODY,
        "include_name": True,
        "channels":     None,
    },
    "multiplier_reminder": {
        "title":        MSG.MULTIPLIER_REMINDER_TITLE,
        "body":         MSG.MULTIPLIER_REMINDER_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Social Follow ──────────────────────────────────────────────────────────
    "social_follow": {
        "title":        MSG.HP_EARNED_SOCIAL_TITLE,
        "body":         MSG.HP_EARNED_SOCIAL_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── First-Order Gift ───────────────────────────────────────────────────────
    "first_order_gift": {
        "title":        MSG.FIRST_ORDER_GIFT_TITLE,
        "body":         MSG.FIRST_ORDER_GIFT_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Alias types — keep notif_type used in codebase, map to registry templates ─

    # referral_completed was used before referral_hp_earned was standardised
    "referral_completed": {
        "title":        MSG.REFERRAL_HP_EARNED_TITLE,
        "body":         MSG.REFERRAL_HP_EARNED_BODY,
        "include_name": True,
        "channels":     None,
    },
    # streak_cycle_failed is the code's notif_type; login_streak_cycle_failed is canonical
    "streak_cycle_failed": {
        "title":        MSG.NOTIF_LOGIN_STREAK_CYCLE_FAILED_TITLE,
        "body":         MSG.NOTIF_LOGIN_STREAK_CYCLE_FAILED_BODY,
        "include_name": True,
        "channels":     None,
    },
    # hp_transfer_recipient — used in hp.py for the receiving side of a transfer
    # (matches EMAIL_TYPES and spec canonical name; hp_received was the old alias)
    "hp_transfer_recipient": {
        "title":        MSG.HP_TRANSFER_RECEIVED_TITLE,
        "body":         MSG.HP_TRANSFER_RECEIVED_BODY,
        "include_name": True,
        "channels":     None,
    },
    # squad_order is the legacy notif_type for squad member added
    "squad_order": {
        "title":        MSG.NOTIF_SQUAD_MEMBER_ADDED_TITLE,
        "body":         MSG.SQUAD_ORDER_ADDED_BODY,
        "include_name": True,
        "channels":     None,
    },
    # order_lock_redeemed (HP reward path) — discount path uses order_lock_redeemed_discount
    "order_lock_redeemed": {
        "title":        MSG.ORDER_LOCK_REDEEMED_HP_TITLE,
        "body":         MSG.ORDER_LOCK_REDEEMED_HP_BODY,
        "include_name": True,
        "channels":     ["push", "in_app"],   # No email — per spec
    },

    # ── Gift service ───────────────────────────────────────────────────────────
    "gift_granted": {
        "title":        MSG.GIFT_KITCHEN_TITLE,
        "body":         MSG.GIFT_KITCHEN_BODY,
        "include_name": False,   # kitchen/admin notification
        "channels":     None,
    },
    "gift_rider_assigned": {
        "title":        MSG.GIFT_ASSIGNED_TITLE,
        "body":         MSG.GIFT_ASSIGNED_BODY,
        "include_name": True,
        "channels":     None,
    },
    "gift_returned": {
        "title":        MSG.GIFT_RETURNED_TITLE,
        "body":         MSG.GIFT_RETURNED_BODY,
        "include_name": True,
        "channels":     None,
    },

    # ── Rewards ────────────────────────────────────────────────────────────────
    "reward_status": {
        # {name} here is the reward name, not the user's name — include_name=False
        "title":        MSG.REWARD_STATUS_TITLE,
        "body":         MSG.REWARD_STATUS_BODY,
        "include_name": False,
        "channels":     None,
    },
    "new_reward": {
        # {name} here is the reward name — include_name=False prevents user-name injection
        "title":        MSG.REWARD_NEW_TITLE,
        "body":         MSG.REWARD_NEW_BODY,
        "include_name": False,
        "channels":     None,
    },

    # ── Admin / operational ────────────────────────────────────────────────────
    "catering_request": {
        "title":        MSG.EVENT_CATERING_TITLE,
        "body":         MSG.EVENT_CATERING_BODY,
        "include_name": False,   # admin notification
        "channels":     None,
    },
    "marketplace_request": {
        "title":        MSG.MARKETPLACE_VENDOR_REQUEST_TITLE,
        "body":         MSG.MARKETPLACE_VENDOR_REQUEST_BODY,
        "include_name": False,   # admin notification
        "channels":     None,
    },
    "marketplace_purchase_status": {
        "title":        MSG.MARKETPLACE_PURCHASE_STATUS_TITLE,
        "body":         MSG.MARKETPLACE_PURCHASE_STATUS_BODY,
        "include_name": True,
        "channels":     None,
    },
    "low_inventory": {
        "title":        MSG.MARKETPLACE_LOW_INVENTORY_TITLE,
        "body":         MSG.MARKETPLACE_LOW_INVENTORY_BODY,
        "include_name": False,   # admin notification
        "channels":     None,
    },
    "webhook_failure": {
        "title":        MSG.WEBHOOK_ADMIN_FAILURE_TITLE,
        "body":         MSG.WEBHOOK_ADMIN_FAILURE_BODY,
        "include_name": False,   # admin notification
        "channels":     None,
    },
    "birthday_report": {
        # Body is dynamically constructed at the call site — title only from MSG.
        # Callers pass body= directly (legacy path) alongside notif_type.
        "title":        MSG.BIRTHDAY_REPORT_TITLE,
        "body":         "",   # caller provides body via legacy path
        "include_name": False,
        "channels":     None,
    },

    # ── Non-personalized: Admin/System ─────────────────────────────────────────
    "system_announcement": {
        "title":        MSG.NOTIF_SYSTEM_TITLE,
        "body":         MSG.NOTIF_SYSTEM_BODY,
        "include_name": False,
        "channels":     None,
    },
    "blast": {
        "title":        MSG.NOTIF_SYSTEM_TITLE,   # overridden at call site via title=
        "body":         MSG.NOTIF_SYSTEM_BODY,    # overridden at call site via body=
        "include_name": False,
        "channels":     None,
    },

    # ── Post-Delivery Sequence (RUN 8) ─────────────────────────────────────────
    # 8.1 — Sent immediately when order is marked delivered
    "order_thank_you": {
        "title":        MSG.ORDER_THANK_YOU_TITLE,
        "body":         MSG.ORDER_THANK_YOU_BODY,
        "include_name": True,
        "channels":     ["push", "in_app"],
    },
    # 8.2 — Sent ~2 hours after delivery via check_post_delivery_nudges cron
    "satisfaction_check": {
        "title":        MSG.SATISFACTION_CHECK_TITLE,
        "body":         MSG.SATISFACTION_CHECK_BODY,
        "include_name": True,
        "channels":     ["push", "in_app"],
    },
    # 8.3 — Sent ~24 hours after delivery via check_post_delivery_nudges cron
    "reengagement_nudge": {
        "title":        MSG.REENGAGEMENT_NUDGE_TITLE,
        "body":         MSG.REENGAGEMENT_NUDGE_BODY,
        "include_name": True,
        "channels":     ["in_app"],
    },
}


# ── Public API ─────────────────────────────────────────────────────────────────

def render_notification_template(
    notif_type: str,
    template_data: dict,
) -> "tuple | None":
    """
    Render a notification template for the given type.

    Returns (title, body, include_name, channels_override) on success,
    or None if the send should be skipped (critical field missing or type unknown).

    Args:
        notif_type:    Notification type key (e.g. "order_confirmed").
        template_data: Dict of values to substitute into the template.
                       May include 'name' (injected upstream when include_name=True).

    Critical-field rule (RUN 4.3):
        If any critical placeholder appears in the template strings but is absent
        from template_data, the notification is skipped and None is returned.

    Non-critical-field rule (RUN 4.2):
        If a non-critical placeholder is absent, the value from NON_CRITICAL_FALLBACKS
        is used instead.
    """
    tmpl = NOTIFICATION_TEMPLATES.get(notif_type)
    if tmpl is None:
        # Type not registered — caller must supply title/body directly.
        return None

    title_tmpl: str = tmpl["title"]
    body_tmpl: str = tmpl["body"]
    include_name: bool = tmpl.get("include_name", True)
    channels_override = tmpl.get("channels")  # None or explicit list

    # Collect all placeholder keys referenced in title + body
    all_keys = _placeholders(title_tmpl) | _placeholders(body_tmpl)

    # Build render context from template_data
    ctx: dict = dict(template_data or {})

    for key in all_keys:
        if key in ctx:
            continue  # already provided — use it

        if key in CRITICAL_FIELDS:
            # Missing critical field → skip send (RUN 4.3)
            logger.error(
                "notification_templates: SKIPPING type=%s — critical field {%s} "
                "missing from template_data. template_data keys: %s",
                notif_type,
                key,
                sorted(ctx.keys()),
            )
            return None

        # Non-critical → apply fallback (RUN 4.2)
        fallback = NON_CRITICAL_FALLBACKS.get(key, "")
        ctx[key] = fallback

    try:
        title = title_tmpl.format(**ctx)
        body = body_tmpl.format(**ctx)
    except (KeyError, ValueError) as exc:
        logger.error(
            "notification_templates: format error for type=%s: %s",
            notif_type,
            exc,
        )
        return None

    return title, body, include_name, channels_override


def get_include_name(notif_type: str) -> bool:
    """
    Return the include_name flag for a notification type.
    Defaults to True (personalized) for any type not in the registry.
    """
    tmpl = NOTIFICATION_TEMPLATES.get(notif_type)
    if tmpl is not None:
        return tmpl.get("include_name", True)
    return notif_type not in _NON_PERSONALIZED_TYPES
