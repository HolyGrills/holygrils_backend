"""Rewards store routes — list, redeem, flash sales."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_auth, require_role
from app.services.hp_service import spend_hp, get_hp_balance, get_user_tier
from app.services.notification_service import send_notification
from app.db import get_db
from app.messages import MSG, resolve_msg
import uuid
from datetime import datetime, timezone

rewards_bp = Blueprint("rewards", __name__)


def _is_flash_active(reward: dict, now: datetime) -> bool:
    """Compute flash availability without making the frontend duplicate rules."""
    if reward.get("flash_enabled") not in (True, "true", "True", 1, "1"):
        return False
    try:
        if int(reward.get("flash_slots_remaining") or 0) <= 0:
            return False
        starts_at = reward.get("flash_starts_at")
        ends_at = reward.get("flash_ends_at")
        if not starts_at or not ends_at:
            return False
        def parse(value):
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return parse(starts_at) <= now <= parse(ends_at)
    except (TypeError, ValueError, OverflowError):
        return False


def _with_flash_status(reward: dict, now: datetime) -> dict:
    result = dict(reward)
    result["is_flash_active"] = _is_flash_active(result, now)
    return result


@rewards_bp.route("", methods=["GET"])
def list_rewards():
    """
    List active rewards. Optionally filter by category.
    ---
    tags: [Rewards]
    security: []
    parameters:
      - in: query
        name: category
        type: string
      - in: query
        name: available_only
        type: boolean
        default: true
    responses:
      200:
        description: List of rewards
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    q = db.table("rewards").select("*,hp_tiers(name,slug)").eq("is_active", "true")

    reward_type = request.args.get("category") or request.args.get("reward_type")
    if reward_type:
        q = q.eq("reward_type", reward_type)

    q = q.order("hp_cost")
    rewards = q.execute()
    result = []
    for r in rewards:
        stock = r.get("stock_quantity")
        expires_at = r.get("expires_at")
        if stock is not None and stock <= 0:
            continue
        if expires_at and expires_at < now:
            continue
        result.append(_with_flash_status(r, datetime.now(timezone.utc)))
    return jsonify(result), 200


@rewards_bp.route("/<reward_id>", methods=["GET"])
def get_reward(reward_id):
    """
    Get reward detail.
    ---
    tags: [Rewards]
    security: []
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
    responses:
      200:
        description: Reward detail
      404:
        description: Not found
    """
    db = get_db()
    reward = db.table("rewards").select("*,hp_tiers(name,slug)").eq("id", reward_id).single().execute()
    if not reward:
        return jsonify({"error": MSG.REWARD_NOT_FOUND}), 404
    return jsonify(_with_flash_status(reward, datetime.now(timezone.utc))), 200


@rewards_bp.route("/<reward_id>/redeem", methods=["POST"])
@require_auth
def redeem_reward(reward_id):
    """
    Redeem a reward using HP. Checks balance, quantity, tier eligibility.
    ---
    tags: [Rewards]
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
    responses:
      201:
        description: Redemption successful
      400:
        description: Insufficient HP or reward not available
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    reward = db.table("rewards").select("*").eq("id", reward_id).single().execute()
    if not reward or not reward.get("is_active", True):
        return jsonify({"error": MSG.REWARD_NOT_AVAILABLE}), 404

    stock = reward.get("stock_quantity")
    if stock is not None and stock <= 0:
        return jsonify({"error": MSG.REWARD_OUT_OF_STOCK}), 400

    expires_at = reward.get("expires_at")
    if expires_at and expires_at < now:
        return jsonify({"error": MSG.REWARD_EXPIRED}), 400

    if reward.get("min_tier_id"):
        user_tier = get_user_tier(g.user_id)
        user_tier_order = user_tier["tier"].get("sort_order", 0) if user_tier.get("tier") else 0
        all_tiers = db.table("hp_tiers").select("id,sort_order").execute()
        req_tier = next((t for t in all_tiers if t["id"] == reward["min_tier_id"]), None)
        if req_tier and user_tier_order < req_tier.get("sort_order", 0):
            return jsonify({"error": MSG.REWARD_TIER_TOO_LOW}), 400

    hp_cost = reward["hp_cost"]
    balance = get_hp_balance(g.user_id)
    if balance["active"] < hp_cost:
        return jsonify({"error": resolve_msg(MSG.REWARD_INSUFFICIENT_HP, need=hp_cost, have=balance["active"])}), 400

    redemption = db.table("reward_redemptions").insert({
        "user_id": g.user_id,
        "reward_id": reward_id,
        "hp_cost_snapshot": hp_cost,
        "status": "pending",
    })
    redemption_row = redemption[0] if isinstance(redemption, list) else redemption
    redemption_id = redemption_row["id"]

    try:
        spend_hp(
            user_id=g.user_id,
            amount=hp_cost,
            reference_id=redemption_id,
            reference_type="reward_redemption",
            notes=f"Redeemed: {reward['name']}",
        )
    except ValueError as e:
        db.table("reward_redemptions").eq("id", redemption_id).delete()
        return jsonify({"error": str(e)}), 400

    if stock is not None:
        db.table("rewards").eq("id", reward_id).update({"stock_quantity": stock - 1})

    send_notification(
        user_id=g.user_id,
        notif_type="reward_redeemed",
        template_data={"name": reward["name"], "hp": hp_cost},
        reference_id=redemption_id,
        reference_type="reward_redemption",
    )

    return jsonify({"redemption": redemption_row, "hp_spent": hp_cost}), 201


@rewards_bp.route("/admin/redemptions", methods=["GET"])
@require_role("admin")
def admin_list_redemptions():
    """
    List all reward redemptions across all users (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, fulfilled, rejected]
      - in: query
        name: reward_id
        type: string
        description: Filter by reward
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
        description: All redemptions for admin
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("reward_redemptions").select(
        "*,rewards(name,reward_type,hp_cost,image_url),profiles!user_id(full_name,email)"
    )
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    reward_id = request.args.get("reward_id")
    if reward_id:
        q = q.eq("reward_id", reward_id)
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"redemptions": rows, "count": len(rows)}), 200


@rewards_bp.route("/admin/redemptions/<redemption_id>", methods=["PATCH"])
@require_role("admin")
def admin_update_redemption(redemption_id):
    """
    Fulfil or reject a reward redemption (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: path
        name: redemption_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [status]
          properties:
            status: {type: string, enum: [fulfilled, rejected]}
            admin_notes: {type: string}
            fulfilled_at: {type: string, format: date-time, description: "Defaults to now"}
    responses:
      200:
        description: Redemption updated
      400:
        description: Invalid status
      404:
        description: Redemption not found
    """
    db = get_db()
    row = db.table("reward_redemptions").select("id,status,user_id,reward_id").eq("id", redemption_id).single().execute()
    if not row:
        return jsonify({"error": MSG.REWARD_REDEMPTION_NOT_FOUND}), 404
    data = request.get_json(force=True) or {}
    new_status = data.get("status", "").strip()
    if new_status not in ("fulfilled", "rejected"):
        return jsonify({"error": MSG.REWARD_REDEMPTION_INVALID_STATUS}), 400
    update = {"status": new_status}
    if new_status == "fulfilled":
        from datetime import datetime, timezone
        update["fulfilled_at"] = data.get("fulfilled_at") or datetime.now(timezone.utc).isoformat()
    result = db.table("reward_redemptions").eq("id", redemption_id).update(update)
    # Notify the user
    try:
        reward = db.table("rewards").select("name").eq("id", row["reward_id"]).single().execute()
        from app.services.notification_service import send_notification
        send_notification(
            user_id=row["user_id"],
            notif_type="reward_status",
            template_data={"name": reward.get("name", "reward"), "status": new_status},
        )
    except Exception:
        pass
    return jsonify(result[0] if isinstance(result, list) else result), 200


@rewards_bp.route("", methods=["POST"])
@require_role("admin")
def create_reward():
    """
    Create a new reward (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name, hp_cost, category]
          properties:
            name: {type: string}
            hp_cost: {type: integer}
            category: {type: string, enum: [food, merch, experience, marketplace]}
            quantity_available: {type: integer}
            min_tier_id: {type: string}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
    responses:
      201:
        description: Reward created
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["name", "hp_cost"]
    for f in required:
        if data.get(f) is None:
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=f)}), 400
    if "category" in data and "reward_type" not in data:
        data["reward_type"] = data.pop("category")
    # quantity_available is the API name; DB column is stock_quantity
    if "quantity_available" in data:
        data["stock_quantity"] = data.pop("quantity_available")
    data["is_active"] = data.get("is_active", True)
    result = db.table("rewards").insert(data)
    created = result[0] if isinstance(result, list) else result

    # Notify all active users about the new reward
    try:
        reward_name = created.get("name") or data.get("name", "New reward")
        active_users = (
            db.table("profiles")
            .select("id")
            .eq("is_active", "true")
            .eq("role", "student")
            .execute()
        ) or []
        for user in active_users:
            send_notification(
                user_id=user["id"],
                notif_type="new_reward",
                template_data={"name": reward_name},
                reference_id=created.get("id"),
                reference_type="reward",
            )
    except Exception:
        pass

    return jsonify(created), 201


@rewards_bp.route("/<reward_id>", methods=["PATCH"])
@require_role("admin")
def update_reward(reward_id):
    """
    Update a reward (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            hp_cost: {type: integer}
            is_active: {type: boolean}
            quantity_available: {type: integer}
            ends_at: {type: string, format: date-time}
    responses:
      200:
        description: Reward updated
    """
    db = get_db()
    data = request.get_json(force=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("rewards").eq("id", reward_id).update(data)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@rewards_bp.route("/<reward_id>", methods=["DELETE"])
@require_role("admin")
def delete_reward(reward_id):
    """
    Deactivate (soft-delete) a reward (admin only).
    ---
    tags: [Rewards]
    parameters:
      - in: path
        name: reward_id
        type: string
        required: true
    responses:
      200:
        description: Reward deactivated
      404:
        description: Reward not found
    """
    db = get_db()
    existing = db.table("rewards").select("id").eq("id", reward_id).limit(1).execute()
    if not existing:
        return jsonify({"error": MSG.REWARD_NOT_FOUND}), 404
    db.table("rewards").eq("id", reward_id).update({
        "is_active": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": MSG.REWARD_DEACTIVATED, "reward_id": reward_id}), 200


@rewards_bp.route("/redemptions", methods=["GET"])
@require_auth
def my_redemptions():
    """
    Get authenticated user's reward redemption history.
    ---
    tags: [Rewards]
    responses:
      200:
        description: Redemption history
    """
    db = get_db()
    redemptions = (
        db.table("reward_redemptions")
        .select("*,rewards(name,reward_type,hp_cost,image_url)")
        .eq("user_id", g.user_id)
        .order("created_at", ascending=False)
        .execute()
    )
    return jsonify(redemptions), 200
    
