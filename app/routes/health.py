"""
Health check route — GET /api/health

Returns the API version, uptime status, and live connectivity checks for
every external dependency (Supabase, Redis).  Designed to be polled by
load balancers, uptime monitors, and deployment pipelines.

Response shape:
    {
        "status": "ok" | "degraded",
        "api": "<APP_NAME from config>",
        "version": "1.0.0",
        "checks": {
            "supabase": "connected" | "error:<status>" | "unreachable:<msg>",
            "redis":    "connected" | "error:<msg>"    | "not_configured"
        }
    }

HTTP 200 is returned whether status is "ok" or "degraded" — callers must
inspect the "status" field.  A 503 is only returned when the health handler
itself crashes, which should never happen in practice.
"""

import os

import requests as _req
from flask import Blueprint, jsonify, current_app
from app.messages import MSG

health_bp = Blueprint("health", __name__)


@health_bp.route("/health")
def health():
    """
    API health check — connectivity to Supabase and Redis.
    ---
    tags: [Health]
    security: []
    responses:
      200:
        description: Health status (inspect 'status' field — may be 'ok' or 'degraded')
        schema:
          properties:
            status:  {type: string, example: ok}
            api:     {type: string, example: "My App", description: "APP_NAME from config"}
            version: {type: string, example: "1.0.0"}
            checks:  {type: object}
    """
    checks: dict = {}

    # ── Supabase ──────────────────────────────────────────────────────────────
    try:
        url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        r = _req.get(
            f"{url}/rest/v1/profiles?select=id&limit=1",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=5,
        )
        checks["supabase"] = MSG.HEALTH_CONNECTED if r.status_code < 400 else f"error:{r.status_code}"
    except Exception as exc:
        checks["supabase"] = f"unreachable:{str(exc)[:80]}"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        try:
            import redis as _redis
            client = _redis.from_url(redis_url, socket_connect_timeout=3)
            client.ping()
            checks["redis"] = MSG.HEALTH_CONNECTED
        except Exception as exc:
            checks["redis"] = f"error:{str(exc)[:80]}"
    else:
        checks["redis"] = MSG.HEALTH_NOT_CONFIGURED

    overall = MSG.HEALTH_OK if all(
        v in (MSG.HEALTH_CONNECTED, MSG.HEALTH_NOT_CONFIGURED) for v in checks.values()
    ) else MSG.HEALTH_DEGRADED

    return jsonify({
        "status": overall,
        "api": current_app.config.get("APP_NAME", "Holy Grills"),
        "version": MSG.API_VERSION,
        "checks": checks,
    }), 200
