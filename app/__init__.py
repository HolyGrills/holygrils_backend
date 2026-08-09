import uuid
import logging

from flask import Flask, request
from flask_cors import CORS
from flasgger import Swagger

from app.config import Config
from app.utils.logger import get_logger
from app.routes.health import health_bp
from app.routes.auth import auth_bp
from app.routes.menu import menu_bp
from app.routes.orders import orders_bp
from app.routes.hp import hp_bp
from app.routes.wallet import wallet_bp
from app.routes.rewards import rewards_bp
from app.routes.marketplace import marketplace_bp
from app.routes.events import events_bp
from app.routes.referrals import referrals_bp
from app.routes.notifications import notifications_bp, push_bp
from app.routes.admin import admin_bp
from app.routes.kitchen import kitchen_bp
from app.routes.riders import riders_bp
from app.routes.leaderboard import leaderboard_bp
from app.routes.webhooks import webhooks_bp
from app.routes.storefront import storefront_bp
from app.routes.analytics import analytics_bp
from app.routes.cart import cart_bp
from app.routes.saved_for_later import saved_bp
from app.routes.order_locks import order_locks_bp
from app.routes.admin_gifts import admin_gifts_bp
from app.routes.delivery import delivery_bp
from app.routes.graduation import graduation_bp
from app.routes.departments import departments_bp, admin_departments_bp
from app.routes.academic_levels import academic_levels_bp, admin_academic_levels_bp
from app.routes.daily_checkin import checkin_bp
from app.routes.free_sides import free_sides_bp
from app.routes.exclusive_spin import exclusive_spin_bp
from app.routes.admin_feature_flags import admin_flags_bp
from app.routes.uploads import uploads_bp


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    swagger_config = {
        "headers": [],
        "specs": [
            {
                "endpoint": "apispec",
                "route": "/api/docs/apispec.json",
                "rule_filter": lambda rule: True,
                "model_filter": lambda tag: True,
            }
        ],
        "static_url_path": "/api/docs/static",
        "swagger_ui": True,
        "specs_route": "/api/docs/",
    }
    import os as _os
    _app_name = _os.environ.get("APP_NAME", "Holy Grills")
    swagger_template = {
        "swagger": "2.0",
        "info": {
            "title": f"{_app_name} API",
            "description": f"Backend API for the {_app_name} platform — HP economy, food ordering, marketplace, events, wallet, and admin operations.",
            "version": "1.0.0",
            "contact": {"email": _os.environ.get("SWAGGER_CONTACT_EMAIL", "dev@example.com")},
        },
        "securityDefinitions": {
            "BearerAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": "JWT Bearer token. Format: 'Bearer <token>'",
            }
        },
        "security": [{"BearerAuth": []}],
        "basePath": "/api",
        "consumes": ["application/json"],
        "produces": ["application/json"],
    }
    Swagger(app, config=swagger_config, template=swagger_template)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(menu_bp, url_prefix="/api/menu")
    app.register_blueprint(orders_bp, url_prefix="/api/orders")
    app.register_blueprint(hp_bp, url_prefix="/api/hp")
    app.register_blueprint(wallet_bp, url_prefix="/api/wallet")
    app.register_blueprint(rewards_bp, url_prefix="/api/rewards")
    app.register_blueprint(marketplace_bp, url_prefix="/api/marketplace")
    app.register_blueprint(events_bp, url_prefix="/api/events")
    app.register_blueprint(referrals_bp, url_prefix="/api/referrals")
    app.register_blueprint(notifications_bp, url_prefix="/api/notifications")
    app.register_blueprint(push_bp, url_prefix="/api/push")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(kitchen_bp, url_prefix="/api/kitchen")
    app.register_blueprint(riders_bp, url_prefix="/api/riders")
    app.register_blueprint(leaderboard_bp, url_prefix="/api/leaderboard")
    app.register_blueprint(webhooks_bp, url_prefix="/api/webhooks")
    app.register_blueprint(storefront_bp, url_prefix="/api/storefront")
    app.register_blueprint(analytics_bp, url_prefix="/api/analytics")
    app.register_blueprint(cart_bp, url_prefix="/api/cart")
    app.register_blueprint(saved_bp, url_prefix="/api/saved")
    app.register_blueprint(order_locks_bp, url_prefix="/api/order-locks")
    app.register_blueprint(admin_gifts_bp, url_prefix="/api/admin")
    app.register_blueprint(delivery_bp, url_prefix="/api/delivery")
    app.register_blueprint(graduation_bp, url_prefix="/api/graduation")
    app.register_blueprint(departments_bp, url_prefix="/api/departments")
    app.register_blueprint(admin_departments_bp, url_prefix="/api/admin")
    app.register_blueprint(academic_levels_bp, url_prefix="/api/academic-levels")
    app.register_blueprint(admin_academic_levels_bp, url_prefix="/api/admin")
    app.register_blueprint(checkin_bp, url_prefix="/api/checkin")
    app.register_blueprint(free_sides_bp, url_prefix="/api/free-sides")
    app.register_blueprint(exclusive_spin_bp, url_prefix="/api/exclusive-spin")
    app.register_blueprint(admin_flags_bp, url_prefix="/api/admin")
    app.register_blueprint(uploads_bp, url_prefix="/api/upload")
    app.register_blueprint(health_bp, url_prefix="/api")

    _logger = get_logger("holy_grills.app")

    @app.before_request
    def _attach_request_id():
        request.request_id = str(uuid.uuid4())[:8]

    @app.errorhandler(405)
    def method_not_allowed(e):
        rid = getattr(request, "request_id", "-")
        return {"error": "Method not allowed", "message": str(e), "request_id": rid}, 405

    @app.errorhandler(400)
    def bad_request(e):
        rid = getattr(request, "request_id", "-")
        _logger.warning("[%s] 400 Bad Request: %s %s — %s", rid, request.method, request.path, e)
        return {"error": "Bad request", "message": str(e), "request_id": rid}, 400

    @app.errorhandler(401)
    def unauthorized(e):
        rid = getattr(request, "request_id", "-")
        _logger.warning("[%s] 401 Unauthorized: %s %s", rid, request.method, request.path)
        return {"error": "Unauthorized", "message": str(e), "request_id": rid}, 401

    @app.errorhandler(403)
    def forbidden(e):
        rid = getattr(request, "request_id", "-")
        _logger.warning("[%s] 403 Forbidden: %s %s", rid, request.method, request.path)
        return {"error": "Forbidden", "message": str(e), "request_id": rid}, 403

    @app.errorhandler(404)
    def not_found(e):
        rid = getattr(request, "request_id", "-")
        _logger.info("[%s] 404 Not Found: %s %s", rid, request.method, request.path)
        return {"error": "Not found", "message": str(e), "request_id": rid}, 404

    @app.errorhandler(500)
    def internal_error(e):
        rid = getattr(request, "request_id", "-")
        _logger.error("[%s] 500 Internal Server Error: %s %s — %s", rid, request.method, request.path, e)
        return {"error": "Internal server error", "message": str(e), "request_id": rid}, 500

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        rid = getattr(request, "request_id", "-")
        _logger.exception("[%s] Unhandled exception on %s %s", rid, request.method, request.path)
        return {"error": "An unexpected error occurred", "request_id": rid}, 500

    return app
