"""
Graduation route — final-year HP milestone claim.

POST /graduation/claim
  Validates:
    1. academic_level >= graduation_min_level (from system_settings, default 400)
    2. graduation_claimed = false (one-time only)
  Awards: 1000 HP → Active
  Sets:   profiles.graduation_claimed = true
  Fires:  graduation badge trigger
"""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth
from app.db import get_db
from app.messages import MSG, resolve_msg
from app.services.hp_service import award_active_hp
from datetime import datetime, timezone

graduation_bp = Blueprint("graduation", __name__)

# HP awarded on graduation claim — read from config/env so admin can adjust without deploy.
# Falls back to 1000 if GRADUATION_HP env var is not set.
# Not subject to the HP multiplier (use apply_multiplier=False).
_GRADUATION_HP_DEFAULT = 1000


@graduation_bp.route("/claim", methods=["POST"])
@require_auth
def claim_graduation():
    """
    Claim the graduation HP bonus. One-time only.
    Requires academic_level (on user profile) >= graduation_min_level setting.
    ---
    tags: [Graduation]
    responses:
      200:
        description: Graduation HP claimed
      400:
        description: Not eligible or already claimed
    """
    db = get_db()

    # Fetch user profile
    profile = (
        db.table("profiles")
        .select("id,academic_level,graduation_claimed,full_name")
        .eq("id", g.user_id)
        .single()
        .execute()
    )
    if not profile:
        return jsonify({"error": MSG.GRADUATION_PROFILE_NOT_FOUND}), 404

    # Check already claimed
    if profile.get("graduation_claimed"):
        return jsonify({"error": MSG.GRADUATION_ALREADY_CLAIMED}), 400

    # Read minimum level from system_settings (default 400)
    try:
        setting = (
            db.table("system_settings")
            .select("value")
            .eq("key", "graduation_min_level")
            .single()
            .execute()
        )
        graduation_min_level = int((setting or {}).get("value", "400") or "400")
    except Exception:
        graduation_min_level = 400

    # Validate academic_level
    user_level = int(profile.get("academic_level") or 0)
    if user_level < graduation_min_level:
        return jsonify({
            "error": MSG.GRADUATION_LEVEL_REQUIRED.format(required=graduation_min_level, actual=user_level),
            "required_level": graduation_min_level,
            "your_level": user_level,
        }), 400

    # HP amount: read from env/config so it can be changed without a deploy
    graduation_hp = int(current_app.config.get("GRADUATION_HP", _GRADUATION_HP_DEFAULT))

    # Award HP — not subject to HP multiplier (graduation is a fixed life event)
    award_result = award_active_hp(
        user_id=g.user_id,
        amount=graduation_hp,
        txn_type="earn_graduation",
        reference_type="graduation",
        notes=f"Graduation milestone HP — Level {user_level}",
        apply_multiplier=False,
    )

    # Mark claimed
    db.table("profiles").eq("id", g.user_id).update({
        "graduation_claimed": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    # Notify
    try:
        from app.services.notification_service import send_notification
        name = (profile.get("full_name") or "").split()[0] or "Graduate"
        send_notification(
            user_id=g.user_id,
            notif_type="graduation_hp",
            template_data={"name": name, "hp": graduation_hp, "level": user_level},
        )
    except Exception:
        pass

    return jsonify({
        "message": resolve_msg(MSG.GRADUATION_CLAIMED_OK),
        "hp_awarded": award_result.get("awarded", graduation_hp),
        "academic_level": user_level,
    }), 200
