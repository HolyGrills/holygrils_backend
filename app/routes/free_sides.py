"""
Free side credit routes.

GET  /api/free-sides          — check my free side credits
POST /api/free-sides/redeem   — redeem a free side credit at checkout
"""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.db import get_db
from app.messages import MSG, resolve_msg
from app.utils.logger import get_logger
from datetime import datetime, timezone

logger = get_logger(__name__)

free_sides_bp = Blueprint("free_sides", __name__)


def _get_free_side_options() -> list:
    """Fetch allowed side options — from system_settings first, then config fallback."""
    try:
        db = get_db()
        row = db.table("system_settings").select("value").eq("key", "free_side_options").single().execute()
        if row and row.get("value"):
            import json
            return json.loads(row["value"])
    except Exception:
        pass
    return current_app.config.get("FREE_SIDE_OPTIONS", ["Fries", "Coleslaw", "Plantain", "Gizzard"])


def _active_credits(db, user_id: str) -> list:
    """Return non-expired rows from free_side_credits with remaining credits > 0."""
    now = datetime.now(timezone.utc).isoformat()
    return (
        db.table("free_side_credits")
        .select("id,credits_remaining,source,month,expires_at")
        .eq("user_id", user_id)
        .gt("credits_remaining", 0)
        .gte("expires_at", now)
        .order("expires_at")
        .execute()
    ) or []


@free_sides_bp.route("", methods=["GET"])
@require_auth
def my_free_sides():
    """
    Return the authenticated user's free side credit balance and active rows.
    ---
    tags: [FreeSides]
    responses:
      200:
        description: Free side credit summary
    """
    user_id = g.user_id
    db = get_db()

    credits = _active_credits(db, user_id)
    total = sum(r.get("credits_remaining", 0) for r in credits)
    options = _get_free_side_options()

    return jsonify({
        "total_credits": total,
        "credits": credits,
        "available_sides": options,
    }), 200


@free_sides_bp.route("/redeem", methods=["POST"])
@require_auth
def redeem_free_side():
    """
    Redeem one free side credit.
    Body: { "side_choice": "Fries", "order_id": "<uuid>" }
    ---
    tags: [FreeSides]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [side_choice]
          properties:
            side_choice: {type: string}
            order_id: {type: string, format: uuid}
    responses:
      200:
        description: Credit redeemed
      400:
        description: Invalid choice or no credits
    """
    user_id = g.user_id
    db = get_db()
    data = request.get_json(force=True, silent=True) or {}

    side_choice = (data.get("side_choice") or "").strip()
    if not side_choice:
        return jsonify({"error": MSG.FREE_SIDE_INVALID_CHOICE}), 400

    options = _get_free_side_options()
    if side_choice not in options:
        return jsonify({"error": MSG.FREE_SIDE_INVALID_CHOICE, "available": options}), 400

    credits = _active_credits(db, user_id)
    if not credits:
        return jsonify({"error": MSG.FREE_SIDE_NO_CREDITS}), 400

    # Use oldest-expiring credit first
    credit_row = credits[0]
    new_remaining = credit_row["credits_remaining"] - 1

    try:
        db.table("free_side_credits").eq("id", credit_row["id"]).update({
            "credits_remaining": new_remaining,
            "used_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.error("redeem_free_side: update failed for user %s: %s", user_id, e)
        return jsonify({"error": "Could not redeem credit — please try again"}), 500

    return jsonify({
        "message": MSG.FREE_SIDE_REDEEMED,
        "side_choice": side_choice,
        "credits_remaining": new_remaining,
        "order_id": data.get("order_id"),
    }), 200
