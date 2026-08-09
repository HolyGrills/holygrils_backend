"""Admin-only direct-upload helpers."""

import hashlib
import hmac
import time

from flask import Blueprint, current_app, jsonify, request

from app.middleware.auth import require_role

uploads_bp = Blueprint("uploads", __name__)


@uploads_bp.route("/signature", methods=["POST"])
@require_role("admin")
def upload_signature():
    """Generate a short-lived Cloudinary signature for a direct client upload."""
    cloud_name = current_app.config.get("CLOUDINARY_CLOUD_NAME")
    api_key = current_app.config.get("CLOUDINARY_API_KEY")
    api_secret = current_app.config.get("CLOUDINARY_API_SECRET")
    if not cloud_name or not api_key or not api_secret:
        return jsonify({"error": "Cloudinary upload is not configured"}), 503

    data = request.get_json(silent=True) or {}
    folder = str(data.get("folder") or "general").strip()
    if not folder or len(folder) > 255 or folder.startswith("/") or ".." in folder:
        return jsonify({"error": "Invalid upload folder"}), 400

    timestamp = int(time.time())
    params_to_sign = {"folder": folder, "timestamp": timestamp}
    canonical = "&".join(
        f"{key}={params_to_sign[key]}" for key in sorted(params_to_sign)
    )
    signature = hmac.new(
        api_secret.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()

    return jsonify({
        "signature": signature,
        "timestamp": timestamp,
        "api_key": api_key,
        "cloud_name": cloud_name,
        "folder": folder,
    }), 200