"""
Daily check-in routes — separate from login streak.

POST /api/checkin          — record today's check-in
GET  /api/checkin/history  — return check-in history for authenticated user
"""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.db import get_db
from app.messages import MSG, resolve_msg
from app.utils.logger import get_logger
from datetime import datetime, timezone, date

logger = get_logger(__name__)

checkin_bp = Blueprint("daily_checkin", __name__)

# HP awarded per daily check-in (configurable via system_settings later)
_DEFAULT_CHECKIN_HP = 5


def _get_checkin_hp() -> int:
    try:
        db = get_db()
        row = db.table("system_settings").select("value").eq("key", "daily_checkin_hp").single().execute()
        if row and row.get("value"):
            return int(row["value"])
    except Exception:
        pass
    return _DEFAULT_CHECKIN_HP


@checkin_bp.route("", methods=["POST"])
@require_auth
def record_checkin():
    """
    Record daily check-in for the authenticated user.
    One check-in per calendar day (UTC). Awards a small HP bonus if configured.
    ---
    tags: [DailyCheckin]
    responses:
      200:
        description: Already checked in today
      201:
        description: Check-in recorded, HP awarded
      409:
        description: Already checked in today
    """
    user_id = g.user_id
    db = get_db()
    today = date.today().isoformat()

    # Idempotency check
    existing = (
        db.table("daily_checkins")
        .select("id,checkin_date")
        .eq("user_id", user_id)
        .eq("checkin_date", today)
        .execute()
    )
    if existing and len(existing) > 0:
        return jsonify({"message": MSG.CHECKIN_ALREADY_DONE, "already_checked_in": True}), 200

    hp = _get_checkin_hp()

    try:
        db.table("daily_checkins").insert({
            "user_id": user_id,
            "checkin_date": today,
        })
    except Exception as e:
        logger.error("record_checkin: insert failed for user %s: %s", user_id, e)
        # If unique constraint, someone beat us (race); return 200
        return jsonify({"message": MSG.CHECKIN_ALREADY_DONE, "already_checked_in": True}), 200

    # Award HP if configured
    hp_awarded = 0
    if hp > 0:
        try:
            from app.services.hp_service import award_active_hp
            award_active_hp(
                user_id=user_id,
                amount=hp,
                source_type="daily_checkin",
                reference_type="daily_checkin",
                reference_id=today,
                notes=f"Daily check-in bonus — {today}",
            )
            hp_awarded = hp
        except Exception as e:
            logger.warning("record_checkin: HP award failed for user %s: %s", user_id, e)

    return jsonify({
        "message": resolve_msg(MSG.CHECKIN_HP_AWARDED, hp=hp_awarded) if hp_awarded else MSG.CHECKIN_SUCCESS,
        "checkin_date": today,
        "hp_awarded": hp_awarded,
    }), 201


@checkin_bp.route("/history", methods=["GET"])
@require_auth
def checkin_history():
    """
    Return daily check-in history for the authenticated user.
    ---
    tags: [DailyCheckin]
    parameters:
      - in: query
        name: limit
        type: integer
        default: 30
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: Check-in history list
    """
    user_id = g.user_id
    db = get_db()
    limit = min(int(request.args.get("limit", 30)), 90)
    offset = int(request.args.get("offset", 0))

    rows = (
        db.table("daily_checkins")
        .select("id,checkin_date,created_at")
        .eq("user_id", user_id)
        .order("checkin_date", ascending=False)
        .limit(limit)
        .offset(offset)
        .execute()
    ) or []

    today = date.today().isoformat()
    checked_in_today = any(r.get("checkin_date") == today for r in rows)

    return jsonify({
        "checkins": rows,
        "total": len(rows),
        "checked_in_today": checked_in_today,
    }), 200
