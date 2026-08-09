"""
tests/test_phase3_features.py — Unit & integration tests for Phase 3 features.

Tests (all offline / pure Python — no live server required):
  1. Daily check-in blueprint imports and route registration
  2. Feature flags blueprint imports and route registration
  3. Free side credits blueprint imports and route registration
  4. Exclusive spin blueprint imports and route registration
  5. Menu variation DELETE endpoints registered
  6. Event ticket tiers blueprint routes registered
  7. Resend email module loads with correct functions
  8. send_email_raw function signature
  9. Messages — all Phase 3 MSG constants present
   10. Config — exclusive spin validity and SQUAD_ORDER_MAX_ITEMS present
  11. Admin feature flags blueprint routes
  12. Leaderboard prize fulfillment routes
  13. Hall-of-Fame reward routes
  14. Checkin history route
  15. Free side options fallback
  16. Exclusive spin prize draw weighted random
  17. Squad max items config value
  18. Notification channel rules — email reserved for critical types
  19. Order service VALID_TRANSITIONS completeness
  20. HP service imports without error

Run:
    python -m pytest tests/test_phase3_features.py -v
"""

import pytest
import os
import random
from unittest.mock import patch, MagicMock


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """Create a minimal Flask app with mocked Supabase so no real DB calls."""
    os.environ.setdefault("SUPABASE_URL", "https://mock.supabase.co")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "mock-srk")
    os.environ.setdefault("SUPABASE_ANON_KEY", "mock-anon")
    os.environ.setdefault("SECRET_KEY", "test-secret")
    os.environ.setdefault("JWT_SECRET", "test-jwt-secret")

    from app import create_app
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# ── 1. Blueprint Imports ───────────────────────────────────────────────────────

class TestBlueprintImports:
    def test_daily_checkin_blueprint_imports(self):
        from app.routes.daily_checkin import checkin_bp
        assert checkin_bp is not None
        assert checkin_bp.name == "daily_checkin"

    def test_feature_flags_blueprint_imports(self):
        from app.routes.admin_feature_flags import admin_flags_bp
        assert admin_flags_bp is not None

    def test_free_sides_blueprint_imports(self):
        from app.routes.free_sides import free_sides_bp
        assert free_sides_bp is not None

    def test_exclusive_spin_blueprint_imports(self):
        from app.routes.exclusive_spin import exclusive_spin_bp
        assert exclusive_spin_bp is not None


# ── 2. Route Registration ─────────────────────────────────────────────────────

class TestRouteRegistration:
    def test_checkin_routes_registered(self, app):
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/api/checkin" in rules
        assert "/api/checkin/history" in rules

    def test_free_sides_routes_registered(self, app):
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/api/free-sides" in rules
        assert "/api/free-sides/redeem" in rules

    def test_exclusive_spin_routes_registered(self, app):
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/api/exclusive-spin" in rules
        assert "/api/exclusive-spin/spin" in rules
        assert "/api/exclusive-spin/buy" not in rules

    def test_feature_flags_routes_registered(self, app):
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/api/admin/feature-flags" in rules
        assert "/api/admin/feature-flags/<flag_name>" in rules
        assert "/api/admin/leaderboard-prizes" in rules
        assert "/api/admin/hall-of-fame-rewards" in rules

    def test_variation_delete_routes_registered(self, app):
        """DELETE endpoints for variation groups and options must be registered."""
        rule_map = {}
        for r in app.url_map.iter_rules():
            rule_map.setdefault(r.rule, set()).update(r.methods)
        vg = "/api/menu/items/<item_id>/variation-groups/<group_id>"
        vo = "/api/menu/items/<item_id>/variation-groups/<group_id>/options/<option_id>"
        assert "DELETE" in rule_map.get(vg, set()), f"DELETE not in {rule_map.get(vg)}"
        assert "DELETE" in rule_map.get(vo, set()), f"DELETE not in {rule_map.get(vo)}"

    def test_event_tier_routes_registered(self, app):
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/api/events/<event_id>/tiers" in rules
        assert "/api/events/tiers/<tier_id>" in rules

    def test_event_registrants_routes_registered(self, app):
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/api/events/<event_id>/registrants" in rules
        assert "/api/events/<event_id>/send-registrants-to-host" in rules

    def test_leaderboard_prizes_routes_registered(self, app):
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/api/admin/leaderboard-prizes" in rules
        assert "/api/admin/leaderboard-prizes/<record_id>" in rules

    def test_hof_rewards_routes_registered(self, app):
        rules = {r.rule for r in app.url_map.iter_rules()}
        assert "/api/admin/hall-of-fame-rewards" in rules
        assert "/api/admin/hall-of-fame-rewards/<record_id>" in rules


# ── 3. Resend Email Module ────────────────────────────────────────────────────

class TestResendEmailModule:
    def test_send_email_imports(self):
        from app.utils.email import send_email
        assert callable(send_email)

    def test_send_email_raw_imports(self):
        from app.utils.email import send_email_raw
        assert callable(send_email_raw)

    def test_send_email_raw_signature(self):
        import inspect
        from app.utils.email import send_email_raw
        sig = inspect.signature(send_email_raw)
        params = list(sig.parameters.keys())
        assert "to_email" in params
        assert "to_name" in params
        assert "subject" in params
        assert "html_body" in params

    def test_send_email_signature(self):
        import inspect
        from app.utils.email import send_email
        sig = inspect.signature(send_email)
        params = list(sig.parameters.keys())
        assert "to_email" in params
        assert "to_name" in params
        assert "template_key" in params

    def test_send_email_returns_false_without_api_key(self):
        """Without RESEND_API_KEY, send_email_raw must return False gracefully."""
        from app.utils.email import send_email_raw
        with patch.dict(os.environ, {"RESEND_API_KEY": ""}):
            result = send_email_raw(
                to_email="test@example.com",
                to_name="Test",
                subject="Test Subject",
                html_body="<p>Hello</p>",
            )
        assert result is False

    def test_send_email_unknown_template_returns_false(self):
        """Unknown template key must return False without crashing."""
        from app.utils.email import send_email
        with patch.dict(os.environ, {"RESEND_API_KEY": ""}):
            result = send_email(
                to_email="test@example.com",
                to_name="Test",
                template_key="definitely_not_a_real_template_key",
                data={},
            )
        assert result is False

    def test_templates_dict_contains_expected_keys(self):
        from app.utils.email import TEMPLATES
        expected = [
            "order_confirmed", "hp_earned", "tier_upgrade", "wallet_funded",
            "password_reset", "birthday_bonus", "referral_completed",
            "abandoned_cart", "reward_redeemed",
        ]
        for key in expected:
            assert key in TEMPLATES, f"Missing email template: {key}"

    def test_each_template_has_subject_and_body(self):
        from app.utils.email import TEMPLATES
        for key, tmpl in TEMPLATES.items():
            assert "subject" in tmpl, f"Template '{key}' missing 'subject'"
            assert "body" in tmpl, f"Template '{key}' missing 'body'"
            assert callable(tmpl["body"]), f"Template '{key}' body must be callable"


# ── 4. MSG Constants ──────────────────────────────────────────────────────────

class TestMsgConstants:
    def test_checkin_messages_present(self):
        from app.messages import MSG
        assert hasattr(MSG, "CHECKIN_ALREADY_DONE")
        assert hasattr(MSG, "CHECKIN_SUCCESS")
        assert hasattr(MSG, "CHECKIN_HP_AWARDED")

    def test_free_side_messages_present(self):
        from app.messages import MSG
        assert hasattr(MSG, "FREE_SIDE_INVALID_CHOICE")
        assert hasattr(MSG, "FREE_SIDE_NO_CREDITS")
        assert hasattr(MSG, "FREE_SIDE_REDEEMED")

    def test_spin_messages_present(self):
        from app.messages import MSG
        assert hasattr(MSG, "SPIN_NO_CREDITS")

    def test_feature_flag_messages_present(self):
        from app.messages import MSG
        assert hasattr(MSG, "FEATURE_FLAG_NOT_FOUND")
        assert hasattr(MSG, "FEATURE_FLAG_UPDATED")

    def test_hof_messages_present(self):
        from app.messages import MSG
        assert hasattr(MSG, "HOF_REWARD_NOT_FOUND")
        assert hasattr(MSG, "HOF_REWARD_FULFILLED")

    def test_resolve_msg_handles_missing_placeholders(self):
        from app.messages import resolve_msg
        # Should not raise even with unknown placeholders
        result = resolve_msg("Hello {name}, you have {hp} HP")
        assert "Hello" in result
        assert "HP" in result


# ── 5. Config Values ──────────────────────────────────────────────────────────

class TestConfig:
    def test_squad_order_max_items_in_config(self, app):
        assert "SQUAD_ORDER_MAX_ITEMS" in app.config
        assert isinstance(app.config["SQUAD_ORDER_MAX_ITEMS"], int)
        assert app.config["SQUAD_ORDER_MAX_ITEMS"] >= 3

    def test_squad_order_min_items_lte_max(self, app):
        min_items = app.config.get("SQUAD_ORDER_MIN_ITEMS", 3)
        max_items = app.config.get("SQUAD_ORDER_MAX_ITEMS", 20)
        assert min_items <= max_items, "Min items must not exceed max items"

    def test_exclusive_spin_validity_days(self, app):
        days = app.config.get("EXCLUSIVE_SPIN_VALIDITY_DAYS", 30)
        assert days > 0

    def test_free_side_options_config(self, app):
        opts = app.config.get("FREE_SIDE_OPTIONS", ["Fries"])
        assert isinstance(opts, list)
        assert len(opts) > 0


# ── 6. Exclusive Spin Prize Draw ─────────────────────────────────────────────

class TestExclusiveSpinPrizeDraw:
    def test_draw_prize_returns_string(self, app):
        with app.app_context():
            from app.routes.exclusive_spin import _draw_prize, _spin_prizes
            prize = _draw_prize(_spin_prizes())
        assert isinstance(prize, str)
        assert len(prize) > 0

    def test_draw_prize_with_empty_list_uses_fallback(self):
        from app.routes.exclusive_spin import _draw_prize
        prize = _draw_prize([])
        assert isinstance(prize, str)

    def test_draw_prize_only_returns_valid_prizes(self, app):
        with app.app_context():
            from app.routes.exclusive_spin import _draw_prize, _spin_prizes
            prizes = _spin_prizes()
            valid_names = {p["name"] for p in prizes}
            for _ in range(50):
                result = _draw_prize(prizes)
                assert result in valid_names, f"Got unexpected prize: {result}"

    def test_spin_prizes_have_name_and_weight(self, app):
        with app.app_context():
            from app.routes.exclusive_spin import _spin_prizes
            prizes = _spin_prizes()
        assert len(prizes) >= 5
        for p in prizes:
            assert "name" in p, f"Prize missing 'name': {p}"
            assert "weight" in p, f"Prize missing 'weight': {p}"
            assert p["weight"] > 0


# ── 7. Free Side Options ─────────────────────────────────────────────────────

class TestFreeSideOptions:
    def test_get_free_side_options_returns_list(self, app):
        with app.app_context():
            from app.routes.free_sides import _get_free_side_options
            with patch("app.routes.free_sides.get_db") as mock_db:
                mock_db.return_value.table.return_value.select.return_value \
                    .eq.return_value.single.return_value.execute.side_effect = Exception("DB error")
                opts = _get_free_side_options()
        assert isinstance(opts, list)
        assert len(opts) > 0


# ── 8. Notification Channel Rules ────────────────────────────────────────────

class TestNotificationChannelRules:
    """Email channel must only be sent for critical notification types."""

    # Actual EMAIL_TYPES from notification_service.py
    CRITICAL_TYPES = {
        "order_confirmed", "order_delivered", "order_refunded",
        "hp_decay_applied", "tier_downgrade", "birthday_bonus",
        "password_reset", "wallet_funded_card", "wallet_funded_bank",
    }

    def test_critical_types_get_email_channel(self):
        from app.services.notification_service import get_notification_channels
        for ntype in self.CRITICAL_TYPES:
            channels = get_notification_channels(ntype)
            assert "email" in channels, f"Critical type '{ntype}' missing email channel"

    def test_non_critical_types_no_email(self):
        from app.services.notification_service import get_notification_channels
        non_critical = ["order_preparing", "hp_earned", "leaderboard_updated", "squad_invite"]
        for ntype in non_critical:
            channels = get_notification_channels(ntype)
            assert "email" not in channels, f"Non-critical type '{ntype}' should not have email"

    def test_order_confirmed_always_gets_email(self):
        from app.services.notification_service import get_notification_channels
        assert "email" in get_notification_channels("order_confirmed")

    def test_order_delivered_always_gets_email(self):
        from app.services.notification_service import get_notification_channels
        assert "email" in get_notification_channels("order_delivered")

    def test_push_always_included(self):
        from app.services.notification_service import get_notification_channels
        for ntype in ["order_confirmed", "order_preparing", "hp_earned"]:
            channels = get_notification_channels(ntype)
            assert "push" in channels


# ── 9. Order State Machine ────────────────────────────────────────────────────

class TestOrderStateMachine:
    def test_valid_transitions_imported(self):
        from app.services.order_service import VALID_TRANSITIONS
        assert isinstance(VALID_TRANSITIONS, dict)

    def test_all_terminal_states_have_empty_transitions(self):
        from app.services.order_service import VALID_TRANSITIONS
        terminal = {"cancelled", "refunded"}
        for state in terminal:
            assert VALID_TRANSITIONS.get(state) == [], \
                f"Terminal state '{state}' must have no transitions"

    def test_delivered_state_exists(self):
        from app.services.order_service import VALID_TRANSITIONS
        assert "delivered" in VALID_TRANSITIONS

    def test_received_can_go_to_preparing(self):
        from app.services.order_service import VALID_TRANSITIONS
        assert "preparing" in VALID_TRANSITIONS.get("received", [])

    def test_received_can_be_cancelled(self):
        from app.services.order_service import VALID_TRANSITIONS
        assert "cancelled" in VALID_TRANSITIONS.get("received", [])


# ── 10. HP Service Imports ────────────────────────────────────────────────────

class TestHPServiceImports:
    def test_award_active_hp_importable(self):
        from app.services.hp_service import award_active_hp
        assert callable(award_active_hp)

    def test_spend_hp_importable(self):
        from app.services.hp_service import spend_hp
        assert callable(spend_hp)

    def test_earn_pending_hp_importable(self):
        from app.services.hp_service import earn_pending_hp
        assert callable(earn_pending_hp)


# ── 11. Daily Checkin Logic ───────────────────────────────────────────────────

class TestDailyCheckinLogic:
    def test_checkin_endpoint_requires_auth(self, client):
        """POST /api/checkin without token must return 401."""
        resp = client.post("/api/checkin")
        assert resp.status_code == 401

    def test_checkin_history_requires_auth(self, client):
        """GET /api/checkin/history without token must return 401."""
        resp = client.get("/api/checkin/history")
        assert resp.status_code == 401


# ── 12. Exclusive Spin Endpoints Auth ────────────────────────────────────────

class TestExclusiveSpinAuth:
    def test_get_spins_requires_auth(self, client):
        resp = client.get("/api/exclusive-spin")
        assert resp.status_code == 401

    def test_do_spin_requires_auth(self, client):
        resp = client.post("/api/exclusive-spin/spin")
        assert resp.status_code == 401

    def test_buy_spin_endpoint_removed(self, client):
        resp = client.post("/api/exclusive-spin/buy")
        assert resp.status_code == 404


# ── 13. Free Sides Endpoints Auth ────────────────────────────────────────────

class TestFreeSidesAuth:
    def test_get_free_sides_requires_auth(self, client):
        resp = client.get("/api/free-sides")
        assert resp.status_code == 401

    def test_redeem_free_side_requires_auth(self, client):
        resp = client.post("/api/free-sides/redeem", json={"side_choice": "Fries"})
        assert resp.status_code == 401


# ── 14. Feature Flags Endpoints Auth ─────────────────────────────────────────

class TestFeatureFlagsAuth:
    def test_list_feature_flags_requires_admin(self, client):
        """Non-admin or unauthenticated calls must be rejected."""
        resp = client.get("/api/admin/feature-flags")
        assert resp.status_code in (401, 403)

    def test_update_feature_flag_requires_admin(self, client):
        resp = client.patch("/api/admin/feature-flags/spin_and_win", json={"is_active": False})
        assert resp.status_code in (401, 403)


# ── 15. Event Tiers Public Access ────────────────────────────────────────────

class TestEventTiersPublicAccess:
    def test_list_tiers_is_public(self, client):
        """GET /api/events/<id>/tiers should be accessible without auth (returns 404 for unknown event)."""
        resp = client.get("/api/events/00000000-0000-0000-0000-000000000000/tiers")
        # 404 = route found, event not found — correct behavior
        assert resp.status_code in (200, 404)

    def test_create_tier_requires_admin(self, client):
        resp = client.post(
            "/api/events/00000000-0000-0000-0000-000000000000/tiers",
            json={"name": "VIP", "price_naira": 5000}
        )
        assert resp.status_code in (401, 403)


# ── 16. Health Endpoint ───────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_health_returns_200_or_503(self, client):
        resp = client.get("/api/health")
        assert resp.status_code in (200, 503)
        data = resp.get_json()
        assert "status" in data
        assert "checks" in data

    def test_health_has_supabase_check(self, client):
        resp = client.get("/api/health")
        data = resp.get_json()
        assert "supabase" in data.get("checks", {})


# ── 17. Variation Delete Routes ───────────────────────────────────────────────

class TestVariationDeleteRoutes:
    def test_delete_variation_group_requires_admin(self, client):
        resp = client.delete(
            "/api/menu/items/00000000-0000-0000-0000-000000000000"
            "/variation-groups/00000000-0000-0000-0000-000000000001"
        )
        assert resp.status_code in (401, 403)

    def test_delete_variation_option_requires_admin(self, client):
        resp = client.delete(
            "/api/menu/items/00000000-0000-0000-0000-000000000000"
            "/variation-groups/00000000-0000-0000-0000-000000000001"
            "/options/00000000-0000-0000-0000-000000000002"
        )
        assert resp.status_code in (401, 403)


# ── 18. Leaderboard Prize Fulfillment Auth ────────────────────────────────────

class TestLeaderboardPrizeFulfillmentAuth:
    def test_list_prizes_requires_admin(self, client):
        resp = client.get("/api/admin/leaderboard-prizes")
        assert resp.status_code in (401, 403)

    def test_fulfill_prize_requires_admin(self, client):
        resp = client.patch(
            "/api/admin/leaderboard-prizes/00000000-0000-0000-0000-000000000000",
            json={"status": "fulfilled"}
        )
        assert resp.status_code in (401, 403)


# ── 19. Squad Max Items Config ────────────────────────────────────────────────

class TestSquadMaxItemsConfig:
    def test_squad_max_items_enforced_in_service(self):
        """Verify SQUAD_ORDER_MAX_ITEMS is read from config in order_service."""
        import inspect
        import app.services.order_service as svc
        src = inspect.getsource(svc)
        assert "SQUAD_ORDER_MAX_ITEMS" in src, \
            "SQUAD_ORDER_MAX_ITEMS must be referenced in order_service.py"

    def test_squad_min_items_enforced_in_service(self):
        import inspect
        import app.services.order_service as svc
        src = inspect.getsource(svc)
        assert "SQUAD_ORDER_MIN_ITEMS" in src, \
            "SQUAD_ORDER_MIN_ITEMS must be referenced in order_service.py"


# ── 20. Notification Templates Registry ──────────────────────────────────────

class TestNotificationTemplatesRegistry:
    def test_notification_templates_module_loads(self):
        from app.services.notification_templates import NOTIFICATION_TEMPLATES
        assert isinstance(NOTIFICATION_TEMPLATES, dict)
        assert len(NOTIFICATION_TEMPLATES) > 0

    def test_all_templates_have_required_keys(self):
        from app.services.notification_templates import NOTIFICATION_TEMPLATES
        for key, tmpl in NOTIFICATION_TEMPLATES.items():
            assert "title" in tmpl or "title_fn" in tmpl, \
                f"Template '{key}' missing title"
            assert "body" in tmpl or "body_fn" in tmpl, \
                f"Template '{key}' missing body"
