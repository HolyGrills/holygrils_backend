"""
Admin — Feature Flags + Leaderboard Prize Fulfilment + Hall of Fame Reward Fulfilment.

GET    /api/admin/feature-flags           — list all flags
GET    /api/admin/feature-flags/<name>    — get one flag
PATCH  /api/admin/feature-flags/<name>    — toggle / update a flag

GET    /api/admin/leaderboard-prizes      — pending prize fulfilments
PATCH  /api/admin/leaderboard-prizes/<id> — mark one fulfilled

GET    /api/admin/hall-of-fame-rewards    — pending HoF box rewards
PATCH  /api/admin/hall-of-fame-rewards/<user_id> — update status
"""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role
from app.db import get_db
from app.messages import MSG
from app.utils.logger import get_logger
from datetime import datetime, timezone

logger = get_logger(__name__)

admin_flags_bp = Blueprint("admin_feature_flags", __name__)


# ── Feature Flags ─────────────────────────────────────────────────────────────

@admin_flags_bp.route("/feature-flags", methods=["POST"])
@require_role("admin")
def create_feature_flag():
    """Create a disabled feature flag."""
    data = request.get_json(force=True, silent=True) or {}
    flag_name = (data.get("feature_name") or "").strip()
    if not flag_name:
        return jsonify({"error": MSG.FEATURE_FLAG_NAME_REQUIRED}), 400

    db = get_db()
    existing = db.table("feature_flags").select("*").eq("feature_name", flag_name).single().execute()
    if existing:
        return jsonify({"error": "Feature flag already exists", "flag": existing}), 409

    payload = {
        "feature_name": flag_name,
        "is_active": bool(data.get("is_active", False)),
        "description": data.get("description"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": g.user_id,
    }
    result = db.table("feature_flags").insert(payload)
    flag = result[0] if isinstance(result, list) else result
    return jsonify({"message": MSG.FEATURE_FLAG_UPDATED, "flag": flag}), 201

@admin_flags_bp.route("/feature-flags", methods=["GET"])
@require_role("admin")
def list_feature_flags():
    """
    List all feature flags.
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: campus_id
        type: string
    responses:
      200:
        description: Feature flag list
    """
    db = get_db()
    q = db.table("feature_flags").select("*").order("feature_name")
    rows = q.execute() or []
    return jsonify(rows), 200


@admin_flags_bp.route("/feature-flags/<flag_name>", methods=["GET"])
@require_role("admin")
def get_feature_flag(flag_name):
    """
    Get a specific feature flag.
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: flag_name
        type: string
        required: true
    responses:
      200:
        description: Flag detail
      404:
        description: Not found
    """
    db = get_db()
    row = db.table("feature_flags").select("*").eq("feature_name", flag_name).single().execute()
    if not row:
        return jsonify({"error": MSG.FEATURE_FLAG_NOT_FOUND}), 404
    return jsonify(row), 200


@admin_flags_bp.route("/feature-flags/<flag_name>", methods=["PATCH"])
@require_role("admin")
def update_feature_flag(flag_name):
    """
    Create or update a feature flag (upsert).
    Body: { "is_active": true, "campus_id": null }
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: flag_name
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            is_active: {type: boolean}
            campus_id: {type: string}
    responses:
      200:
        description: Flag updated
    """
    db = get_db()
    data = request.get_json(force=True, silent=True) or {}

    existing = db.table("feature_flags").select("feature_name").eq("feature_name", flag_name).single().execute()

    now_iso = datetime.now(timezone.utc).isoformat()
    admin_id = g.user_id

    if existing:
        ALLOWED = {"is_active", "description"}
        safe = {k: v for k, v in data.items() if k in ALLOWED}
        safe["updated_at"] = now_iso
        safe["updated_by"] = admin_id
        result = db.table("feature_flags").eq("feature_name", flag_name).update(safe)
        updated = result[0] if isinstance(result, list) else result
    else:
        payload = {
            "feature_name": flag_name,
            "is_active": data.get("is_active", False),
            "description": data.get("description"),
            "updated_at": now_iso,
            "updated_by": admin_id,
        }
        result = db.table("feature_flags").insert(payload)
        updated = result[0] if isinstance(result, list) else result

    return jsonify({"message": MSG.FEATURE_FLAG_UPDATED, "flag": updated}), 200


# ── Leaderboard Prize Fulfilment ──────────────────────────────────────────────

@admin_flags_bp.route("/leaderboard-prizes", methods=["GET"])
@require_role("admin")
def list_leaderboard_prizes():
    """
    List leaderboard prize fulfilment records.
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, fulfilled]
      - in: query
        name: month
        type: string
    responses:
      200:
        description: Prize list
    """
    db = get_db()
    q = db.table("leaderboard_reward_fulfillments").select("*").order("month", ascending=False)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    month = request.args.get("month")
    if month:
        q = q.eq("month", month)
    rows = q.execute() or []

    # Enrich with profile names
    user_ids = list({r["user_id"] for r in rows if r.get("user_id")})
    profiles = {}
    if user_ids:
        prows = db.table("profiles").select("id,full_name,phone").in_("id", user_ids).execute() or []
        profiles = {p["id"]: p for p in prows}

    for r in rows:
        prof = profiles.get(r.get("user_id"), {})
        r["full_name"] = prof.get("full_name")
        r["phone"]     = prof.get("phone")

    return jsonify(rows), 200


@admin_flags_bp.route("/leaderboard-prizes/<record_id>", methods=["PATCH"])
@require_role("admin")
def fulfil_leaderboard_prize(record_id):
    """
    Mark a leaderboard prize as fulfilled.
    Body: { "status": "fulfilled", "notes": "..." }
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: record_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            status: {type: string, enum: [pending, fulfilled, cancelled]}
            notes: {type: string}
    responses:
      200:
        description: Updated
      404:
        description: Not found
    """
    db = get_db()
    row = db.table("leaderboard_reward_fulfillments").select("id").eq("id", record_id).single().execute()
    if not row:
        return jsonify({"error": MSG.LEADERBOARD_REWARD_NOT_FOUND}), 404

    data = request.get_json(force=True, silent=True) or {}
    safe = {k: v for k, v in data.items() if k in {"status", "notes"}}
    safe["fulfilled_by"] = g.user_id
    safe["fulfilled_at"] = datetime.now(timezone.utc).isoformat()

    result = db.table("leaderboard_reward_fulfillments").eq("id", record_id).update(safe)
    updated = result[0] if isinstance(result, list) else result
    return jsonify({"message": MSG.LEADERBOARD_PRIZE_FULFILLED, "record": updated}), 200


# ── Hall of Fame Reward Fulfilment ────────────────────────────────────────────

@admin_flags_bp.route("/hall-of-fame-rewards", methods=["GET"])
@require_role("admin")
def list_hof_rewards():
    """
    List Hall of Fame box reward records.
    ---
    tags: [Admin]
    parameters:
      - in: query
        name: status
        type: string
        enum: [pending, fulfilled, cancelled]
    responses:
      200:
        description: HoF reward list
    """
    db = get_db()
    q = db.table("hall_of_fame_rewards").select("*").order("inducted_at", ascending=False)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    rows = q.execute() or []

    user_ids = list({r["user_id"] for r in rows if r.get("user_id")})
    profiles = {}
    if user_ids:
        prows = db.table("profiles").select("id,full_name,phone,email").in_("id", user_ids).execute() or []
        profiles = {p["id"]: p for p in prows}

    for r in rows:
        prof = profiles.get(r.get("user_id"), {})
        r["full_name"] = prof.get("full_name")
        r["phone"]     = prof.get("phone")
        r["email"]     = prof.get("email")

    return jsonify(rows), 200


@admin_flags_bp.route("/hall-of-fame-rewards/<record_id>", methods=["PATCH"])
@require_role("admin")
def fulfil_hof_reward(record_id):
    """
    Update a Hall of Fame reward record status.
    Body: { "status": "fulfilled", "notes": "..." }
    ---
    tags: [Admin]
    parameters:
      - in: path
        name: record_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            status: {type: string, enum: [pending, fulfilled, cancelled]}
            notes: {type: string}
    responses:
      200:
        description: Updated
      404:
        description: Not found
    """
    db = get_db()
    row = db.table("hall_of_fame_rewards").select("id").eq("id", record_id).single().execute()
    if not row:
        return jsonify({"error": MSG.HOF_REWARD_NOT_FOUND}), 404

    data = request.get_json(force=True, silent=True) or {}
    safe = {k: v for k, v in data.items() if k in {"status", "notes"}}
    safe["fulfilled_by"] = g.user_id
    safe["fulfilled_at"] = datetime.now(timezone.utc).isoformat()

    result = db.table("hall_of_fame_rewards").eq("id", record_id).update(safe)
    updated = result[0] if isinstance(result, list) else result
    return jsonify({"message": MSG.HOF_REWARD_FULFILLED, "record": updated}), 200
