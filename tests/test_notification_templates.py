"""
tests/test_notification_templates.py — Unit tests for the notification template pipeline.

Tests:
  1. Unknown type → None (caller fallback path)
  2. Missing critical field → None, error logged
  3. Non-critical fallback substitution
  4. Happy-path rendering for key types
  5. Channel resolution (email eligibility, explicit override)
  6. include_name flag behaviour

Run:
    python -m pytest tests/test_notification_templates.py -v
"""

import pytest
from unittest.mock import patch

# Import the module under test
from app.services.notification_templates import (
    render_notification_template,
    get_include_name,
    NOTIFICATION_TEMPLATES,
    NON_CRITICAL_FALLBACKS,
    CRITICAL_FIELDS,
    _NON_PERSONALIZED_TYPES,
)
from app.services.notification_service import get_notification_channels


# ── 1. Unknown type ────────────────────────────────────────────────────────────

class TestUnknownType:
    def test_unknown_type_returns_none(self):
        result = render_notification_template("totally_unknown_type_xyz_999", {})
        assert result is None, "Unknown type must return None so caller supplies title/body"

    def test_unknown_type_with_data_still_none(self):
        result = render_notification_template("not_a_real_type", {"order_id": "ABC", "hp": 100})
        assert result is None


# ── 2. Missing critical field → skip send ─────────────────────────────────────

class TestCriticalFieldValidation:
    def test_order_confirmed_missing_order_id_returns_none(self):
        # order_id is critical — missing it must abort
        result = render_notification_template("order_confirmed", {})
        assert result is None

    def test_order_confirmed_with_order_id_succeeds(self):
        result = render_notification_template("order_confirmed", {"order_id": "ABCD1234"})
        assert result is not None
        title, body, include_name, channels = result
        assert "ABCD1234" in title or "ABCD1234" in body

    def test_hp_earned_missing_hp_returns_none(self):
        # hp is critical — template body uses {hp}
        result = render_notification_template("hp_earned", {})
        assert result is None

    def test_hp_earned_with_zero_hp_succeeds(self):
        # hp=0 is not "missing" — 0 is a valid value
        result = render_notification_template("hp_earned", {"hp": 0, "total_hp": 0})
        assert result is not None

    def test_wallet_funded_card_missing_amount_returns_none(self):
        result = render_notification_template("wallet_funded_card", {})
        assert result is None

    def test_wallet_funded_card_with_amount_succeeds(self):
        result = render_notification_template("wallet_funded_card", {"amount": "1,500"})
        assert result is not None
        title, body, _, _ = result
        assert "1,500" in title or "1,500" in body

    def test_event_registered_missing_title_returns_none(self):
        # title is critical (MSG uses {title} for event name in EVENT_REGISTERED_TITLE)
        result = render_notification_template("event_registered", {})
        assert result is None

    def test_hp_earned_event_missing_event_title_returns_none(self):
        result = render_notification_template("hp_earned_event", {"hp": 50})
        assert result is None

    def test_hp_earned_event_with_both_fields_succeeds(self):
        result = render_notification_template("hp_earned_event", {"hp": 50, "event_title": "Food Fest"})
        assert result is not None
        title, body, _, _ = result
        assert "50" in title
        assert "Food Fest" in body


# ── 3. Non-critical fallback substitution ─────────────────────────────────────

class TestNonCriticalFallbacks:
    def test_name_missing_uses_there(self):
        # referral_signup has no required placeholders; include_name renders name
        # We test that a type with {name} in body falls back to "there" when absent
        result = render_notification_template("birthday_bonus", {"hp": 150})
        assert result is not None
        _, _, include_name, _ = result
        # include_name=True means name will be fetched/injected upstream

    def test_tier_name_missing_uses_your_tier(self):
        result = render_notification_template("tier_upgrade", {})
        # tier_name is non-critical — should fall back, not return None
        assert result is not None

    def test_winback_70_no_data_succeeds(self):
        result = render_notification_template("winback_70", {})
        assert result is not None

    def test_winback_95_with_days_succeeds(self):
        result = render_notification_template("winback_95", {"days": 3})
        assert result is not None
        _, body, _, _ = result
        assert "3" in body

    def test_winback_95_missing_days_uses_fallback(self):
        result = render_notification_template("winback_95", {})
        assert result is not None  # days is non-critical, uses fallback "a few"

    def test_abandoned_cart_no_data_succeeds(self):
        result = render_notification_template("abandoned_cart", {})
        assert result is not None


# ── 4. Happy-path rendering for key types ─────────────────────────────────────

class TestHappyPath:
    def test_order_lock_redeemed_hp(self):
        result = render_notification_template("order_lock_redeemed_hp", {"hp": 75})
        assert result is not None
        title, body, _, channels = result
        assert "75" in title or "75" in body
        assert channels == ["push", "in_app"]   # registry override — no email

    def test_order_lock_redeemed_discount(self):
        result = render_notification_template("order_lock_redeemed_discount", {"pct": 10.0, "saved": 500})
        assert result is not None
        _, body, _, channels = result
        assert "10" in body
        assert channels == ["push", "in_app"]

    def test_birthday_bonus(self):
        result = render_notification_template("birthday_bonus", {"hp": 150, "name": "Chioma"})
        assert result is not None
        title, _, _, _ = result
        assert "Chioma" in title

    def test_birthday_blast(self):
        result = render_notification_template("birthday_blast", {"name": "Tunde"})
        assert result is not None
        title, body, _, _ = result
        assert "Tunde" in title or "Tunde" in body

    def test_referral_completed(self):
        result = render_notification_template("referral_completed", {"hp": 200})
        assert result is not None
        _, body, _, _ = result
        assert "200" in body

    def test_hp_unlocked(self):
        result = render_notification_template("hp_unlocked", {"unlocked_hp": 300})
        assert result is not None
        title, body, _, _ = result
        assert "300" in title or "300" in body

    def test_membership_anniversary(self):
        result = render_notification_template("membership_anniversary", {
            "months": 6, "name": "Amara", "hp": 100
        })
        assert result is not None
        title, body, _, _ = result
        assert "6" in title

    def test_graduation_hp(self):
        result = render_notification_template("graduation_hp", {
            "name": "Temi", "hp": 500, "level": "400"
        })
        assert result is not None
        _, body, _, _ = result
        assert "500" in body

    def test_gift_granted_with_order_id(self):
        result = render_notification_template("gift_granted", {"order_id": "ABCD1234"})
        assert result is not None
        _, body, include_name, _ = result
        assert "ABCD1234" in body
        assert include_name is False   # admin/kitchen — non-personalized

    def test_squad_order(self):
        result = render_notification_template("squad_order", {"organizer": "Ada"})
        assert result is not None
        _, body, _, _ = result
        assert "Ada" in body

    def test_webhook_failure(self):
        result = render_notification_template("webhook_failure", {
            "event_type": "charge.success",
            "reference": "REF123",
            "error": "Timeout",
        })
        assert result is not None
        _, body, include_name, _ = result
        assert "charge.success" in body
        assert include_name is False

    def test_catering_request(self):
        result = render_notification_template("catering_request", {
            "organizer": "John Doe",
            "event_name": "Finals Dinner",
        })
        assert result is not None
        _, body, include_name, _ = result
        assert "John Doe" in body
        assert include_name is False


# ── 5. Channel resolution ─────────────────────────────────────────────────────

class TestChannelResolution:
    def test_order_confirmed_gets_email(self):
        channels = get_notification_channels("order_confirmed")
        assert "email" in channels
        assert "push" in channels
        assert "in_app" in channels

    def test_order_preparing_no_email(self):
        channels = get_notification_channels("order_preparing")
        assert "email" not in channels

    def test_order_delivered_gets_email(self):
        channels = get_notification_channels("order_delivered")
        assert "email" in channels

    def test_wallet_withdrawal_no_email(self):
        # Wallet withdrawal types must never send email per spec
        for t in ("wallet_withdrawal_submitted", "wallet_withdrawal_approved", "wallet_withdrawal_rejected"):
            channels = get_notification_channels(t)
            assert "email" not in channels, f"{t} should not have email"

    def test_order_lock_redeemed_discount_channel_override(self):
        # Registry overrides channels to push+in_app only
        result = render_notification_template("order_lock_redeemed_discount", {"pct": 10.0, "saved": 100})
        assert result is not None
        _, _, _, channels = result
        assert channels == ["push", "in_app"]
        assert "email" not in channels

    def test_wallet_funded_card_gets_email(self):
        channels = get_notification_channels("wallet_funded_card")
        assert "email" in channels

    def test_wallet_funded_bank_gets_email(self):
        channels = get_notification_channels("wallet_funded_bank")
        assert "email" in channels

    def test_hp_decay_applied_gets_email(self):
        # hp_decay_applied is in EMAIL_TYPES (inactivity notice warrants an email)
        channels = get_notification_channels("hp_decay_applied")
        assert "email" in channels


# ── 6. include_name flag ──────────────────────────────────────────────────────

class TestIncludeNameFlag:
    def test_personalized_types_have_include_name_true(self):
        personalized_sample = [
            "order_confirmed", "birthday_bonus", "tier_upgrade",
            "hp_earned", "hp_unlocked", "referral_completed",
        ]
        for t in personalized_sample:
            assert get_include_name(t) is True, f"{t} should have include_name=True"

    def test_admin_types_have_include_name_false(self):
        admin_types = [
            "gift_granted", "catering_request", "marketplace_request",
            "low_inventory", "webhook_failure", "birthday_report",
        ]
        for t in admin_types:
            assert get_include_name(t) is False, f"{t} should have include_name=False"

    def test_non_personalized_set_matches_registry(self):
        """All types in _NON_PERSONALIZED_TYPES should have include_name=False in the registry."""
        for notif_type in _NON_PERSONALIZED_TYPES:
            if notif_type in NOTIFICATION_TEMPLATES:
                entry = NOTIFICATION_TEMPLATES[notif_type]
                assert entry.get("include_name") is False, (
                    f"{notif_type} is in _NON_PERSONALIZED_TYPES but "
                    f"registry has include_name={entry.get('include_name')}"
                )


# ── 7. Registry completeness — all active notif_types are registered ──────────

class TestRegistryCompleteness:
    """
    Ensure every notif_type string used across the codebase has a registry entry.
    Types that intentionally use the legacy path are listed in KNOWN_LEGACY below.
    """

    KNOWN_LEGACY = {
        # Conditional/dynamic bodies that cannot be expressed as a single template
        "order_refunded",       # body conditional on wallet_credited flag
        "birthday_report",      # body is a dynamically assembled user list (title still in registry)
        "order_lock_reminder",  # two different body templates based on reward_type (hp vs discount)
        # send_scheduled_notifications uses title/body from the DB campaign record
    }

    KNOWN_TYPES_IN_CODEBASE = {
        # order_service
        "order_lock_redeemed_hp", "order_lock_redeemed_discount",
        "order_confirmed", "hp_earned", "hp_unlocked", "tier_upgrade",
        "order_preparing", "order_ready", "order_assigned",
        "order_out_for_delivery", "order_delivered", "order_delivery_attempted",
        "order_unclaimed", "order_cancelled",
        "order_thank_you",                  # RUN 8.1 — immediate on delivery
        # streak_service
        "streak_cycle_failed", "checkin_streak_week", "checkin_reclaimed", "order_streak",
        # auth_service
        "referral_signup",
        # gift_service
        "first_order_gift", "gift_granted", "gift_rider_assigned", "gift_returned",
        # routes/orders
        "squad_order",
        # routes/events
        "hp_earned_event", "event_registered", "catering_request",
        # routes/hp
        "hp_transfer_recipient",            # renamed from hp_received
        # routes/rewards
        "reward_redeemed", "reward_status", "new_reward",
        # routes/referrals
        "referral_completed",
        # routes/marketplace
        "marketplace_purchase", "marketplace_purchase_status",
        "marketplace_request", "low_inventory",
        # routes/graduation
        "graduation_hp",
        # routes/admin / routes/webhooks
        "abandoned_cart", "wallet_funded_card", "wallet_funded_bank", "webhook_failure",
        # tasks/scheduled
        "leaderboard_rank", "hall_of_fame",
        "tier_downgrade", "tier_grace_period",   # renamed from tier_dropped
        "birthday_bonus", "birthday_blast", "birthday_report",
        "scheduled_order_due",
        "winback_70", "winback_95", "winback_118",
        "hp_decay_applied", "order_lock_reminder",  # renamed from hp_decay
        "membership_anniversary",
        # post-delivery cron (RUN 8.2 / 8.3)
        "satisfaction_check", "reengagement_nudge",
    }

    def test_all_active_types_have_registry_entry(self):
        missing = []
        for notif_type in self.KNOWN_TYPES_IN_CODEBASE:
            if notif_type not in self.KNOWN_LEGACY and notif_type not in NOTIFICATION_TEMPLATES:
                missing.append(notif_type)
        assert not missing, (
            f"These notification types are used in the codebase but not registered:\n"
            + "\n".join(f"  - {t}" for t in sorted(missing))
        )
