"""
Admin Gift routes — manage first-order hot dog gifts and system settings.

GET    /admin/gifts/first-order          — list pending/all first-order gifts
PATCH  /admin/gifts/first-order/<id>     — update gift status (fulfil/cancel)
GET    /admin/settings                   — list all system settings
PATCH  /admin/settings/<key>             — update a system setting
"""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.db import get_db
from app.messages import MSG
from datetime import datetime, timezone

admin_gifts_bp = Blueprint("admin_gifts", __name__)


@admin_gifts_bp.route("/first-order-gifts", methods=["GET"])
@require_auth
@require_role("admin")
def list_first_order_gifts():
    """
    Admin: list first-order gifts with user details.
    ---
    tags: [Admin - Gifts]
    parameters:
      - in: query
        name: status
        type: string
        description: Filter by status (pending, fulfilled, cancelled, claimed, redeemed, returned). Default all.
    responses:
      200:
        description: List of first-order gifts
    """
    db = get_db()
    q = (
        db.table("first_order_gifts")
        .select("*,profiles(full_name,email,phone),orders(id,total_amount,created_at)")
        .order("created_at", ascending=False)
    )
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    gifts = q.execute() or []
    return jsonify({"gifts": gifts, "count": len(gifts)}), 200


@admin_gifts_bp.route("/first-order-gifts/<gift_id>", methods=["PATCH"])
@require_auth
@require_role("admin")
def update_first_order_gift(gift_id):
    """
    Admin: update a first-order gift status.
    ---
    tags: [Admin - Gifts]
    parameters:
      - in: path
        name: gift_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [status]
          properties:
            status: {type: string, enum: [fulfilled, cancelled, claimed, redeemed, returned]}
    responses:
      200:
        description: Gift updated
      400:
        description: Invalid status
      404:
        description: Gift not found
    """
    db = get_db()
    gift = (
        db.table("first_order_gifts")
        .select("id,status")
        .eq("id", gift_id)
        .single()
        .execute()
    )
    if not gift:
        return jsonify({"error": MSG.GIFT_NOT_FOUND}), 404

    data = request.get_json(force=True) or {}
    new_status = (data.get("status") or "").strip()
    if new_status not in ("fulfilled", "cancelled", "claimed", "redeemed", "returned"):
        return jsonify({"error": MSG.GIFT_INVALID_STATUS}), 400

    now = datetime.now(timezone.utc).isoformat()
    update_payload = {"status": new_status}
    if new_status in ("fulfilled", "claimed"):
        update_payload["claimed_at"] = now

    db.table("first_order_gifts").eq("id", gift_id).update(update_payload)
    return jsonify({"message": MSG.GIFT_UPDATED, "status": new_status}), 200


# ── System Settings ───────────────────────────────────────────────────────────

@admin_gifts_bp.route("/settings", methods=["GET"])
@require_auth
@require_role("admin")
def list_settings():
    """
    Admin: list all system settings.
    ---
    tags: [Admin - Settings]
    responses:
      200:
        description: All system settings
    """
    db = get_db()
    settings = db.table("system_settings").select("*").order("key").execute() or []
    return jsonify({"settings": settings, "count": len(settings)}), 200


@admin_gifts_bp.route("/settings/<key>", methods=["PATCH"])
@require_auth
@require_role("admin")
def update_setting(key):
    """
    Admin: update a system setting value.
    ---
    tags: [Admin - Settings]
    parameters:
      - in: path
        name: key
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [value]
          properties:
            value: {type: string}
            description: {type: string}
    responses:
      200:
        description: Setting updated
      400:
        description: Value required
      404:
        description: Setting not found
    """
    db = get_db()
    existing = (
        db.table("system_settings")
        .select("key")
        .eq("key", key)
        .single()
        .execute()
    )
    if not existing:
        return jsonify({"error": MSG.SETTING_NOT_FOUND}), 404

    data = request.get_json(force=True) or {}
    value = data.get("value")
    if value is None:
        return jsonify({"error": MSG.SETTING_VALUE_REQUIRED}), 400
    if key == "hp_multiplier":
        try:
            if float(str(value)) not in (1.0, 2.0):
                return jsonify({"error": "hp_multiplier must be 1 or 2"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "hp_multiplier must be 1 or 2"}), 400

    update_payload = {
        "value": str(value),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": g.user_id,
    }
    if "description" in data:
        update_payload["description"] = data["description"]

    db.table("system_settings").eq("key", key).update(update_payload)

    # When hp_multiplier is set above 1, broadcast to all active users immediately
    if key == "hp_multiplier":
        try:
            mult_val = float(str(value))
            if mult_val > 1.0:
                _broadcast_multiplier_event(db, mult_val)
        except Exception:
            pass  # non-critical — setting is saved regardless

    return jsonify({"message": MSG.SETTING_UPDATED, "key": key, "value": str(value)}), 200


def _broadcast_multiplier_event(db, multiplier: float):
    """Send a push + in-app notification to all active users when a multiplier event goes live."""
    try:
        from app.services.notification_service import send_notification
        from app.messages import MSG
        users = db.table("profiles").select("id").eq("is_active", "true").execute() or []
        for user in users:
            try:
                send_notification(
                    user_id=user["id"],
                    notif_type="multiplier_live",
                    title=MSG.MULTIPLIER_LIVE_TITLE,
                    body=MSG.MULTIPLIER_LIVE_BODY.format(multiplier=multiplier),
                    channels=["push", "in_app"],
                )
            except Exception:
                pass
    except Exception:
        pass


@admin_gifts_bp.route("/settings", methods=["POST"])
@require_auth
@require_role("admin")
def create_setting():
    """
    Admin: create a new system setting.
    ---
    tags: [Admin - Settings]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [key, value]
          properties:
            key: {type: string}
            value: {type: string}
            description: {type: string}
    responses:
      201:
        description: Setting created
      400:
        description: Key and value required
      409:
        description: Key already exists
    """
    db = get_db()
    data = request.get_json(force=True) or {}
    key = (data.get("key") or "").strip()
    value = data.get("value")
    if not key or value is None:
        return jsonify({"error": MSG.SETTING_KEY_VALUE_REQUIRED}), 400

    existing = db.table("system_settings").select("key").eq("key", key).single().execute()
    if existing:
        return jsonify({"error": MSG.SETTING_KEY_EXISTS}), 409

    now = datetime.now(timezone.utc).isoformat()
    result = db.table("system_settings").insert({
        "key": key,
        "value": str(value),
        "description": data.get("description", ""),
        "updated_at": now,
        "updated_by": g.user_id,
    })
    row = result[0] if isinstance(result, list) else result
    return jsonify({"message": MSG.SETTING_CREATED, "setting": row}), 201
