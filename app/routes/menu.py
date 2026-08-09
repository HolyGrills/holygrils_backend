"""Menu routes — categories, items, add-ons, variation groups, daily limits, kitchen capacity."""

from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_role
from app.db import get_db
from datetime import datetime, timezone
from app.messages import MSG


def _log_menu_admin_action(actor_id, entity_type, entity_id, action, before_data=None, after_data=None):
    """Write an admin audit log entry for menu item changes. Silently ignores errors."""
    try:
        from app.db import get_db as _get_db
        db = _get_db()
        db.table("admin_audit_logs").insert({
            "actor_id": actor_id,
            "actor_role": "admin",
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "action": action,
            "before_value": before_data,
            "after_value": after_data,
        })
    except Exception:
        pass


def _notify_sellout(item_id: str, item_name: str):
    """Send a push+in_app notification to all admins when an item sells out."""
    try:
        from app.db import get_db as _get_db
        from app.services.notification_service import send_notification
        db = _get_db()
        admins = (
            db.table("profiles")
            .select("id")
            .eq("role", "admin")
            .eq("is_active", "true")
            .execute()
        ) or []
        for admin in admins:
            send_notification(
                user_id=admin["id"],
                notif_type="menu_item_sold_out",
                title=MSG.MENU_ITEM_SOLD_OUT_TITLE.format(name=item_name),
                body=MSG.MENU_ITEM_SOLD_OUT_BODY.format(name=item_name),
                reference_id=item_id,
                reference_type="menu_item",
                channels=["push", "in_app"],
            )
    except Exception:
        pass

menu_bp = Blueprint("menu", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _today_start_iso():
    """UTC midnight today as ISO string — used to filter today's orders."""
    return datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()


def _kitchen_stats(db):
    """
    Return (capacity, orders_today_count, is_at_capacity).
    capacity is None when the kitchen has no daily cap configured.
    """
    row = (
        db.table("kitchen_settings")
        .select("value")
        .eq("key", "daily_order_capacity")
        .single()
        .execute()
    )
    raw = row.get("value") if row else ""
    capacity = int(raw) if raw and raw.isdigit() else None

    today_orders = (
        db.table("orders")
        .select("id")
        .gte("created_at", _today_start_iso())
        .execute()
    )
    count = len(today_orders) if isinstance(today_orders, list) else 0
    at_capacity = capacity is not None and count >= capacity
    return capacity, count, at_capacity


def _daily_item_counts(db):
    """
    Return {menu_item_id: total_qty_ordered_today} for all of today's orders.
    Aggregation done in Python since the mock client doesn't support GROUP BY.
    """
    today_orders = (
        db.table("orders")
        .select("id")
        .gte("created_at", _today_start_iso())
        .execute()
    ) or []
    order_ids = {o["id"] for o in today_orders}
    counts = {}
    if order_ids:
        rows = db.table("order_items").select("menu_item_id,quantity,order_id").execute() or []
        for row in rows:
            if row.get("order_id") in order_ids and row.get("menu_item_id"):
                mid = row["menu_item_id"]
                counts[mid] = counts.get(mid, 0) + int(row.get("quantity", 1))
    return counts


def _enrich_item(item, counts, at_capacity):
    """Attach is_sold_out and daily_remaining fields to an item dict (mutates)."""
    multiplier = float(item.get("hp_multiplier") or 1.0)
    item["hp_multiplier"] = multiplier
    base_hp = item.get("hp_earn_value") or item.get("hp_earn") or 0
    item["hp_earn_preview"] = round(float(base_hp) * multiplier)
    item["hp_multiplier_badge"] = (
        "2× HP" if multiplier == 2.0 else
        "½ HP" if multiplier == 0.5 else
        f"{multiplier:g}× HP" if multiplier != 1.0 else None
    )
    daily_limit = item.get("daily_limit")
    count = counts.get(item.get("id"), 0)
    if at_capacity:
        item["is_sold_out"] = True
        item["daily_remaining"] = 0
    elif daily_limit is not None:
        remaining = max(0, int(daily_limit) - count)
        item["daily_remaining"] = remaining
        item["is_sold_out"] = remaining == 0
    else:
        item["daily_remaining"] = None
        item["is_sold_out"] = False
    return item


def _review_stats(db, item_ids):
    """Fetch one SQL-aggregated review summary for the requested menu items."""
    if not item_ids:
        return {}
    try:
        rows = db.rpc("get_menu_item_review_stats", {
            "p_item_ids": item_ids,
        }) or []
        if isinstance(rows, dict):
            rows = [rows]
        return {
            row["menu_item_id"]: {
                "avg_rating": float(row.get("avg_rating") or 0),
                "review_count": int(row.get("review_count") or 0),
            }
            for row in rows
            if row.get("menu_item_id")
        }
    except Exception:
        # The migration is applied before production uses this endpoint. Keep
        # older development databases readable while they are being upgraded.
        rows = (
            db.table("order_items")
            .select("menu_item_id,order_id")
            .in_("menu_item_id", item_ids)
            .execute()
        ) or []
        order_ids = list({r["order_id"] for r in rows if r.get("order_id")})
        if not order_ids:
            return {}
        delivered = (
            db.table("orders").select("id").in_("id", order_ids)
            .eq("status", "delivered").execute()
        ) or []
        delivered_ids = {r["id"] for r in delivered}
        reviews = (
            db.table("order_reviews").select("id,order_id,rating")
            .in_("order_id", list(delivered_ids)).not_.is_("rating", "null")
            .execute()
        ) if delivered_ids else []
        review_by_order = {}
        for review in reviews or []:
            review_by_order.setdefault(review["order_id"], []).append(review)
        stats = {}
        for row in rows:
            for review in review_by_order.get(row.get("order_id"), []):
                bucket = stats.setdefault(row["menu_item_id"], [])
                if review.get("rating") is not None:
                    bucket.append((review["id"], float(review["rating"])))
        return {
            item_id: {
                "avg_rating": round(sum(rating for _, rating in values) / len(values), 1),
                "review_count": len({review_id for review_id, _ in values}),
            }
            for item_id, values in stats.items() if values
        }


def _attach_review_stats(items, stats):
    for item in items:
        summary = stats.get(item.get("id"), {})
        item["avg_rating"] = float(summary.get("avg_rating") or 0)
        item["review_count"] = int(summary.get("review_count") or 0)
    return items


# ─────────────────────────────────────────────────────────────────────────────
# Categories
# ─────────────────────────────────────────────────────────────────────────────

@menu_bp.route("/categories", methods=["POST"])
@require_role("admin")
def create_category():
    """
    Create a new menu category (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name, slug]
          properties:
            name: {type: string, example: "Breakfast"}
            slug: {type: string, example: "breakfast"}
            description: {type: string}
            image_url: {type: string}
            sort_order: {type: integer, default: 0}
            is_active: {type: boolean, default: true}
    responses:
      201:
        description: Category created
      400:
        description: Missing required field or slug conflict
    """
    db = get_db()
    data = request.get_json(force=True)
    for f in ["name", "slug"]:
        if not data.get(f):
            return jsonify({"error": f"'{f}' is required"}), 400

    import re as _re
    slug = _re.sub(r"[^a-z0-9-]+", "-", data["slug"].lower()).strip("-")
    existing = db.table("menu_categories").select("id").eq("slug", slug).single().execute()
    if existing:
        return jsonify({"error": MSG.MENU_SLUG_EXISTS.format(slug=slug)}), 400

    record = {
        "name": data["name"],
        "slug": slug,
        "description": data.get("description", ""),
        "sort_order": int(data.get("sort_order", 0)),
        "is_active": bool(data.get("is_active", True)),
    }
    result = db.table("menu_categories").insert(record)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@menu_bp.route("/categories/<category_id>", methods=["PATCH"])
@require_role("admin")
def update_category(category_id):
    """
    Update a menu category (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: category_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            name: {type: string}
            slug: {type: string}
            description: {type: string}
            image_url: {type: string}
            sort_order: {type: integer}
            is_active: {type: boolean}
    responses:
      200:
        description: Category updated
      404:
        description: Category not found
    """
    db = get_db()
    existing = db.table("menu_categories").select("id").eq("id", category_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.MENU_CATEGORY_NOT_FOUND}), 404

    data = request.get_json(force=True)
    allowed = {"name", "slug", "description", "sort_order", "is_active"}
    update = {k: v for k, v in data.items() if k in allowed}
    if not update:
        return jsonify({"error": MSG.MENU_NO_VALID_FIELDS}), 400
    result = db.table("menu_categories").eq("id", category_id).update(update)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@menu_bp.route("/categories/<category_id>", methods=["DELETE"])
@require_role("admin")
def delete_category(category_id):
    """
    Deactivate a menu category (admin only). Does not delete items within it.
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: category_id
        type: string
        required: true
    responses:
      200:
        description: Category deactivated
      404:
        description: Category not found
    """
    db = get_db()
    existing = db.table("menu_categories").select("id,name").eq("id", category_id).single().execute()
    if not existing:
        return jsonify({"error": MSG.MENU_CATEGORY_NOT_FOUND}), 404

    db.table("menu_categories").eq("id", category_id).update({"is_active": False})
    return jsonify({"message": MSG.MENU_CATEGORY_DEACTIVATED.format(name=existing["name"]), "category_id": category_id}), 200


@menu_bp.route("/categories", methods=["GET"])
def list_categories():
    """
    List all active menu categories.
    ---
    tags: [Menu]
    security: []
    responses:
      200:
        description: List of categories
    """
    db = get_db()
    cats = (
        db.table("menu_categories")
        .select("*")
        .eq("is_active", "true")
        .order("sort_order")
        .execute()
    )
    return jsonify(cats), 200


# ─────────────────────────────────────────────────────────────────────────────
# Menu Items
# ─────────────────────────────────────────────────────────────────────────────

@menu_bp.route("/items", methods=["GET"])
def list_items():
    """
    List menu items with availability, daily stock, and kitchen capacity metadata.
    Each item includes is_sold_out and daily_remaining.
    ---
    tags: [Menu]
    security: []
    parameters:
      - in: query
        name: category
        type: string
        description: Filter by category slug
      - in: query
        name: q
        type: string
        description: Search by item name
      - in: query
        name: available_only
        type: boolean
        default: true
    responses:
      200:
        description: |
          { items: [...], kitchen: { daily_order_capacity, orders_today, is_at_capacity } }
    """
    db = get_db()
    q = db.table("menu_items").select("*,menu_categories(name,slug)").is_("deleted_at", "null")

    category_slug = request.args.get("category")
    if category_slug:
        cat = (
            db.table("menu_categories")
            .select("id")
            .eq("slug", category_slug)
            .single()
            .execute()
        )
        if cat:
            q = q.eq("category_id", cat["id"])

    search = request.args.get("q")
    if search:
        q = q.ilike("name", f"%{search}%")

    available_only = request.args.get("available_only", "true").lower() != "false"
    if available_only:
        q = q.eq("is_available", "true")

    # Filter to featured items only (for homepage carousel)
    is_featured = request.args.get("is_featured")
    if is_featured is not None and is_featured.lower() == "true":
        q = q.eq("is_featured", "true")

    items = q.order("name").execute() or []

    capacity, orders_today, at_capacity = _kitchen_stats(db)
    counts = _daily_item_counts(db)
    _attach_review_stats(items, _review_stats(db, [item["id"] for item in items]))
    enriched = [_enrich_item(item, counts, at_capacity) for item in items]

    return jsonify({
        "items": enriched,
        "kitchen": {
            "daily_order_capacity": capacity,
            "orders_today": orders_today,
            "is_at_capacity": at_capacity,
        },
    }), 200


@menu_bp.route("/items/<item_id>", methods=["GET"])
def get_item(item_id):
    """
    Get single menu item detail including variation groups, options, and daily stock.
    ---
    tags: [Menu]
    security: []
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
    responses:
      200:
        description: Menu item with variation_groups and stock info
      404:
        description: Not found
    """
    db = get_db()
    try:
        item = (
            db.table("menu_items")
            .select("*,menu_categories(name,slug)")
            .eq("id", item_id)
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
    except Exception:
        item = (
            db.table("menu_items")
            .select("*,menu_categories(name,slug)")
            .eq("id", item_id)
            .is_("deleted_at", "null")
            .single()
            .execute()
        )
    if not item:
        return jsonify({"error": MSG.MENU_ITEM_NOT_FOUND}), 404

    groups = (
        db.table("menu_item_variation_groups")
        .select("*")
        .eq("menu_item_id", item_id)
        .order("sort_order")
        .execute()
    ) or []
    for group in groups:
        options = (
            db.table("menu_item_variation_options")
            .select("*")
            .eq("variation_group_id", group["id"])
            .order("sort_order")
            .execute()
        ) or []
        group["options"] = options
    item["variation_groups"] = groups

    capacity, _, at_capacity = _kitchen_stats(db)
    counts = _daily_item_counts(db)
    _enrich_item(item, counts, at_capacity)
    _attach_review_stats([item], _review_stats(db, [item_id]))

    return jsonify(item), 200


@menu_bp.route("/items/<item_id>/addons", methods=["GET"])
def get_item_addons(item_id):
    """
    Get add-on groups (e.g. "Sides", "Sauces") for a menu item, each with its
    available add-ons. Use this to render the required-selection popup before
    an item is added to the cart.
    ---
    tags: [Menu]
    security: []
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
    responses:
      200:
        description: List of addon groups, each with an `addons` array
      404:
        description: Menu item not found
    """
    db = get_db()
    item = (
        db.table("menu_items")
        .select("id")
        .eq("id", item_id)
        .is_("deleted_at", "null")
        .single()
        .execute()
    )
    if not item:
        return jsonify({"error": MSG.MENU_ITEM_NOT_FOUND}), 404

    groups = (
        db.table("menu_addon_groups")
        .select("*")
        .eq("menu_item_id", item_id)
        .order("sort_order")
        .execute()
    ) or []
    for group in groups:
        addons = (
            db.table("menu_addons")
            .select("id,name,description,price,is_available,sort_order")
            .eq("group_id", group["id"])
            .eq("is_archived", "false")
            .order("sort_order")
            .execute()
        ) or []
        group["addons"] = addons

    return jsonify({"addon_groups": groups}), 200


@menu_bp.route("/items/<item_id>/addon-groups", methods=["POST"])
@require_role("admin")
def create_addon_group(item_id):
    """
    Create a required (or optional) add-on group on a menu item, e.g.
    "Sides" with min_select=3, max_select=3, is_required=true (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [name]
          properties:
            name: {type: string, example: "Sides"}
            is_required: {type: boolean, default: false}
            min_select: {type: integer, default: 0}
            max_select: {type: integer, default: 1}
            sort_order: {type: integer, default: 0}
    responses:
      201:
        description: Add-on group created
      400:
        description: Missing required field
      404:
        description: Menu item not found
    """
    db = get_db()
    item = db.table("menu_items").select("id").eq("id", item_id).single().execute()
    if not item:
        return jsonify({"error": MSG.MENU_ITEM_NOT_FOUND}), 404

    data = request.get_json(force=True)
    if not data.get("name"):
        return jsonify({"error": MSG.MENU_ADDON_NAME_REQUIRED}), 400

    min_select = int(data.get("min_select", 0))
    max_select = int(data.get("max_select", 1))
    if max_select < min_select:
        return jsonify({"error": MSG.MENU_ADDON_MAX_SELECT_INVALID}), 400

    record = {
        "menu_item_id": item_id,
        "name": data["name"],
        "is_required": bool(data.get("is_required", False)),
        "min_select": min_select,
        "max_select": max_select,
        "sort_order": int(data.get("sort_order", 0)),
    }
    result = db.table("menu_addon_groups").insert(record)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@menu_bp.route("/items/<item_id>/addon-groups/<group_id>", methods=["PATCH"])
@require_role("admin")
def update_addon_group(item_id, group_id):
    """
    Update an add-on group (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: path
        name: group_id
        type: string
        required: true
    responses:
      200:
        description: Add-on group updated
      404:
        description: Add-on group not found
    """
    db = get_db()
    data = request.get_json(force=True)
    allowed = {"name", "is_required", "min_select", "max_select", "sort_order"}
    update = {k: v for k, v in data.items() if k in allowed}
    if "min_select" in update or "max_select" in update:
        existing = (
            db.table("menu_addon_groups")
            .select("min_select,max_select")
            .eq("id", group_id)
            .eq("menu_item_id", item_id)
            .single()
            .execute()
        )
        if not existing:
            return jsonify({"error": MSG.MENU_ADDON_GROUP_NOT_FOUND}), 404
        min_select = int(update.get("min_select", existing["min_select"]))
        max_select = int(update.get("max_select", existing["max_select"]))
        if max_select < min_select:
            return jsonify({"error": MSG.MENU_ADDON_MAX_SELECT_INVALID}), 400
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = (
        db.table("menu_addon_groups")
        .eq("id", group_id)
        .eq("menu_item_id", item_id)
        .update(update)
    )
    if not result:
        return jsonify({"error": MSG.MENU_ADDON_GROUP_NOT_FOUND}), 404
    return jsonify(result[0] if isinstance(result, list) else result), 200


@menu_bp.route("/items/<item_id>/addon-groups/<group_id>", methods=["DELETE"])
@require_role("admin")
def delete_addon_group(item_id, group_id):
    """
    Permanently delete an add-on group and all its linked add-ons (admin only).
    Cascades: menu_addons with group_id = this group are also deleted (ON DELETE CASCADE).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: path
        name: group_id
        type: string
        required: true
    responses:
      200:
        description: Add-on group deleted
      404:
        description: Add-on group not found
    """
    db = get_db()
    existing = (
        db.table("menu_addon_groups")
        .select("id")
        .eq("id", group_id)
        .eq("menu_item_id", item_id)
        .single()
        .execute()
    )
    if not existing:
        return jsonify({"error": MSG.MENU_ADDON_GROUP_NOT_FOUND}), 404
    db.table("menu_addon_groups").eq("id", group_id).eq("menu_item_id", item_id).delete()
    return jsonify({"message": MSG.MENU_ADDON_GROUP_DELETED}), 200


@menu_bp.route("/items", methods=["POST"])
@require_role("admin")
def create_item():
    """
    Create a new menu item (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name, category_id, price]
          properties:
            name: {type: string}
            category_id: {type: string}
            price: {type: number}
            hp_earn_value: {type: integer}
            description: {type: string}
            sku: {type: string}
            dietary_tags: {type: array, items: {type: string}}
            daily_limit: {type: integer, description: "Max servings per day (null = unlimited)"}
    responses:
      201:
        description: Item created
      400:
        description: Missing required field
    """
    db = get_db()
    data = request.get_json(force=True)
    for f in ["name", "category_id", "price"]:
        if data.get(f) is None:
            return jsonify({"error": f"'{f}' is required"}), 400

    data["is_available"] = data.get("is_available", True)
    if "hp_multiplier" in data:
        try:
            data["hp_multiplier"] = float(data["hp_multiplier"])
        except (TypeError, ValueError):
            return jsonify({"error": "hp_multiplier must be 0.5, 1.0, or 2.0"}), 400
        if data["hp_multiplier"] not in {0.5, 1.0, 2.0}:
            return jsonify({"error": "hp_multiplier must be 0.5, 1.0, or 2.0"}), 400
    import re as _re, uuid as _uuid
    if not data.get("slug"):
        base = _re.sub(r"[^a-z0-9]+", "-", data["name"].lower()).strip("-")[:50]
        data["slug"] = f"{base}-{_uuid.uuid4().hex[:5]}"
    # Whitelist: must match menu_items columns exactly as they exist in Supabase
    MENU_ITEM_COLUMNS = {
        "name", "slug", "category_id", "price", "hp_earn_value", "description",
        "tags", "daily_limit", "is_available", "image_url", "is_featured",
        "hp_multiplier",
    }
    safe = {k: v for k, v in data.items() if k in MENU_ITEM_COLUMNS}
    try:
        result = db.table("menu_items").insert(safe)
    except Exception as exc:
        return jsonify({"error": MSG.MENU_ITEM_CREATE_FAILED.format(error=str(exc)[:120])}), 400
    created = result[0] if isinstance(result, list) else result
    _log_menu_admin_action(g.user_id, "menu_items", created.get("id"), "create", after_data=safe)
    return jsonify(created), 201


@menu_bp.route("/items/<item_id>", methods=["PATCH"])
@require_role("admin")
def update_item(item_id):
    """
    Update a menu item (admin only). Supports setting or clearing daily_limit.
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            name: {type: string}
            price: {type: number}
            hp_earn_value: {type: integer}
            is_available: {type: boolean}
            description: {type: string}
            daily_limit: {type: integer, description: "Set to null to remove daily limit"}
    responses:
      200:
        description: Item updated
    """
    # Whitelist for PATCH: only columns that exist in menu_items (Supabase source of truth)
    MENU_ITEM_UPDATE_COLUMNS = {
        "name", "slug", "category_id", "price", "hp_earn_value", "description",
        "tags", "daily_limit", "is_available", "image_url", "is_featured",
        "hp_multiplier",
    }
    db = get_db()
    data = request.get_json(force=True)
    # Fetch before-state for audit and sell-out detection
    before = (
        db.table("menu_items")
        .select("id,name,is_available")
        .eq("id", item_id)
        .single()
        .execute()
    ) or {}
    safe_data = {k: v for k, v in data.items() if k in MENU_ITEM_UPDATE_COLUMNS}
    if "hp_multiplier" in safe_data:
        try:
            safe_data["hp_multiplier"] = float(safe_data["hp_multiplier"])
        except (TypeError, ValueError):
            return jsonify({"error": "hp_multiplier must be 0.5, 1.0, or 2.0"}), 400
        if safe_data["hp_multiplier"] not in {0.5, 1.0, 2.0}:
            return jsonify({"error": "hp_multiplier must be 0.5, 1.0, or 2.0"}), 400
    safe_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("menu_items").eq("id", item_id).update(safe_data)
    data = safe_data  # use safe_data for audit below
    updated = result[0] if isinstance(result, list) else result
    # Audit log
    _log_menu_admin_action(g.user_id, "menu_items", item_id, "update",
                           before_data={"is_available": before.get("is_available"), "name": before.get("name")},
                           after_data={k: v for k, v in data.items() if k != "updated_at"})
    # Sell-out notification: is_available just became False
    was_available = before.get("is_available", True)
    now_available = data.get("is_available")
    if now_available is False and was_available:
        _notify_sellout(item_id, before.get("name", "Item"))
    return jsonify(updated), 200


@menu_bp.route("/items/bulk-availability", methods=["PATCH"])
@require_role("admin")
def bulk_update_availability():
    """
    Bulk update availability for multiple menu items (admin only).
    Use during a rush when multiple items sell out simultaneously.
    ---
    tags: [Menu]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [item_ids, is_available]
          properties:
            item_ids:
              type: array
              items: {type: string}
              description: List of menu item IDs to update
            is_available: {type: boolean}
    responses:
      200:
        description: Items updated
      400:
        description: Missing required fields
    """
    db = get_db()
    data = request.get_json(force=True)
    item_ids = data.get("item_ids")
    if not item_ids or not isinstance(item_ids, list):
        return jsonify({"error": MSG.MENU_ITEM_IDS_REQUIRED}), 400
    if "is_available" not in data:
        return jsonify({"error": MSG.MENU_AVAILABILITY_REQUIRED}), 400

    is_available = bool(data["is_available"])
    # Fetch before-states for sell-out detection (only needed when marking unavailable)
    before_map = {}
    if not is_available:
        before_rows = (
            db.table("menu_items")
            .select("id,name,is_available")
            .in_("id", item_ids)
            .execute()
        ) or []
        before_map = {r["id"]: r for r in before_rows}

    updated = []
    failed = []
    now_ts = datetime.now(timezone.utc).isoformat()
    for item_id in item_ids:
        try:
            db.table("menu_items").eq("id", item_id).update({
                "is_available": is_available,
                "updated_at": now_ts,
            })
            updated.append(item_id)
            _log_menu_admin_action(g.user_id, "menu_items", item_id, "bulk_availability",
                                   before_data={"is_available": before_map.get(item_id, {}).get("is_available")},
                                   after_data={"is_available": is_available})
            # Sell-out notification when availability just turned off
            if not is_available:
                before = before_map.get(item_id, {})
                if before.get("is_available", True):
                    _notify_sellout(item_id, before.get("name", "Item"))
        except Exception as exc:
            failed.append({"id": item_id, "error": str(exc)})

    return jsonify({
        "updated_count": len(updated),
        "failed_count": len(failed),
        "is_available": is_available,
        "updated": updated,
        "failed": failed,
    }), 200


@menu_bp.route("/items/<item_id>/archive", methods=["POST"])
@require_role("admin")
def archive_item(item_id):
    """
    Soft-archive a menu item (admin only). Order history is preserved.
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
    responses:
      200:
        description: Item archived
    """
    db = get_db()
    before = (
        db.table("menu_items")
        .select("id,name,is_available")
        .eq("id", item_id)
        .single()
        .execute()
    ) or {}
    now_ts = datetime.now(timezone.utc).isoformat()
    result = db.table("menu_items").eq("id", item_id).update({
        "deleted_at": now_ts,
        "is_available": False,
    })
    _log_menu_admin_action(g.user_id, "menu_items", item_id, "archive",
                           before_data={"is_available": before.get("is_available"), "name": before.get("name")},
                           after_data={"is_available": False, "deleted_at": now_ts})
    # Sell-out notification only if item was previously available
    if before.get("is_available", True):
        _notify_sellout(item_id, before.get("name", "Item"))
    return jsonify({"message": MSG.MENU_ITEM_ARCHIVED, "item": result[0] if isinstance(result, list) else result}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Variation Groups & Options  (combo side choices)
# ─────────────────────────────────────────────────────────────────────────────

@menu_bp.route("/items/<item_id>/variation-groups", methods=["POST"])
@require_role("admin")
def create_variation_group(item_id):
    """
    Create a variation group on a menu item (admin only).
    Use this when a combo lets customers pick which side accompanies their meal.
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [name]
          properties:
            name: {type: string, example: "Choose your side"}
            is_required: {type: boolean, default: false}
            min_selections: {type: integer, default: 0}
            max_selections: {type: integer, default: 1}
            sort_order: {type: integer, default: 0}
    responses:
      201:
        description: Variation group created
      400:
        description: Missing required field
    """
    db = get_db()
    data = request.get_json(force=True)
    if not data.get("name"):
        return jsonify({"error": MSG.MENU_ADDON_NAME_REQUIRED}), 400

    record = {
        "menu_item_id": item_id,
        "name": data["name"],
        "is_required": bool(data.get("is_required", False)),
        "min_selections": int(data.get("min_selections", 0)),
        "max_selections": int(data.get("max_selections", 1)),
        "sort_order": int(data.get("sort_order", 0)),
    }
    result = db.table("menu_item_variation_groups").insert(record)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@menu_bp.route("/items/<item_id>/variation-groups/<group_id>", methods=["PATCH"])
@require_role("admin")
def update_variation_group(item_id, group_id):
    """
    Update a variation group (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: path
        name: group_id
        type: string
        required: true
    responses:
      200:
        description: Group updated
    """
    db = get_db()
    data = request.get_json(force=True)
    allowed = {"name", "is_required", "min_selections", "max_selections", "sort_order"}
    update = {k: v for k, v in data.items() if k in allowed}
    result = (
        db.table("menu_item_variation_groups")
        .eq("id", group_id)
        .eq("menu_item_id", item_id)
        .update(update)
    )
    return jsonify(result[0] if isinstance(result, list) else result), 200


@menu_bp.route("/items/<item_id>/variation-groups/<group_id>/options", methods=["POST"])
@require_role("admin")
def create_variation_option(item_id, group_id):
    """
    Add a choice option to a variation group (admin only).
    E.g. "Coleslaw" (free), "Plantain" (+₦200).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: path
        name: group_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [name]
          properties:
            name: {type: string, example: "Coleslaw"}
            price_delta: {type: number, default: 0, description: "Extra charge for this choice"}
            is_available: {type: boolean, default: true}
            sort_order: {type: integer, default: 0}
    responses:
      201:
        description: Option created
      400:
        description: Missing required field
    """
    db = get_db()
    data = request.get_json(force=True)
    if not data.get("name"):
        return jsonify({"error": MSG.MENU_ADDON_NAME_REQUIRED}), 400

    record = {
        "variation_group_id": group_id,
        "name": data["name"],
        "price_delta": float(data.get("price_delta", 0)),
        "is_available": bool(data.get("is_available", True)),
        "sort_order": int(data.get("sort_order", 0)),
    }
    result = db.table("menu_item_variation_options").insert(record)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@menu_bp.route("/items/<item_id>/variation-groups/<group_id>/options/<option_id>", methods=["PATCH"])
@require_role("admin")
def update_variation_option(item_id, group_id, option_id):
    """
    Update a variation option (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: path
        name: group_id
        type: string
        required: true
      - in: path
        name: option_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            name: {type: string}
            price_delta: {type: number}
            is_available: {type: boolean}
            sort_order: {type: integer}
    responses:
      200:
        description: Option updated
      404:
        description: Not found
    """
    db = get_db()
    data = request.get_json(force=True)
    allowed = {"name", "price_delta", "is_available", "sort_order"}
    update = {k: v for k, v in data.items() if k in allowed}
    existing = (
        db.table("menu_item_variation_options")
        .select("id")
        .eq("id", option_id)
        .eq("variation_group_id", group_id)
        .single()
        .execute()
    )
    if not existing:
        return jsonify({"error": "Variation option not found"}), 404
    result = (
        db.table("menu_item_variation_options")
        .eq("id", option_id)
        .eq("variation_group_id", group_id)
        .update(update)
    )
    return jsonify(result[0] if isinstance(result, list) else result), 200


@menu_bp.route("/items/<item_id>/variation-groups/<group_id>/options/<option_id>", methods=["DELETE"])
@require_role("admin")
def delete_variation_option(item_id, group_id, option_id):
    """
    Delete a variation option (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: path
        name: group_id
        type: string
        required: true
      - in: path
        name: option_id
        type: string
        required: true
    responses:
      200:
        description: Option deleted
      404:
        description: Not found
    """
    db = get_db()
    existing = (
        db.table("menu_item_variation_options")
        .select("id")
        .eq("id", option_id)
        .eq("variation_group_id", group_id)
        .single()
        .execute()
    )
    if not existing:
        return jsonify({"error": "Variation option not found"}), 404
    db.table("menu_item_variation_options").eq("id", option_id).delete()
    return jsonify({"message": "Variation option deleted"}), 200


@menu_bp.route("/items/<item_id>/variation-groups/<group_id>", methods=["DELETE"])
@require_role("admin")
def delete_variation_group(item_id, group_id):
    """
    Delete a variation group and all its options (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: item_id
        type: string
        required: true
      - in: path
        name: group_id
        type: string
        required: true
    responses:
      200:
        description: Group deleted
      404:
        description: Not found
    """
    db = get_db()
    existing = (
        db.table("menu_item_variation_groups")
        .select("id")
        .eq("id", group_id)
        .eq("menu_item_id", item_id)
        .single()
        .execute()
    )
    if not existing:
        return jsonify({"error": "Variation group not found"}), 404
    # Cascade delete options first
    db.table("menu_item_variation_options").eq("variation_group_id", group_id).delete()
    db.table("menu_item_variation_groups").eq("id", group_id).delete()
    return jsonify({"message": "Variation group and all options deleted"}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Add-Ons  (optional extras for any order)
# ─────────────────────────────────────────────────────────────────────────────

@menu_bp.route("/addons", methods=["GET"])
def list_addons():
    """
    List available add-on items — optional extras customers can append to any order
    (not tied to a specific combo or main item).
    ---
    tags: [Menu]
    security: []
    responses:
      200:
        description: List of add-ons
    """
    db = get_db()
    addons = (
        db.table("menu_addons")
        .select("*")
        .eq("is_archived", "false")
        .eq("is_available", "true")
        .is_("group_id", "null")
        .order("sort_order")
        .execute()
    )
    return jsonify(addons or []), 200


@menu_bp.route("/addons", methods=["POST"])
@require_role("admin")
def create_addon():
    """
    Create an add-on item (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [name, price]
          properties:
            name: {type: string, example: "Extra Sauce"}
            description: {type: string}
            price: {type: number}
            is_available: {type: boolean, default: true}
            sort_order: {type: integer, default: 0}
            group_id: {type: string, description: "Optional — links this add-on into a menu item's add-on group (e.g. 'Sides'). Omit for a global/flat add-on."}
    responses:
      201:
        description: Add-on created
      400:
        description: Missing required field
    """
    db = get_db()
    data = request.get_json(force=True)
    for f in ["name", "price"]:
        if data.get(f) is None:
            return jsonify({"error": f"'{f}' is required"}), 400

    record = {
        "name": data["name"],
        "description": data.get("description", ""),
        "price": float(data["price"]),
        "is_available": bool(data.get("is_available", True)),
        "is_archived": False,
        "sort_order": int(data.get("sort_order", 0)),
    }
    if data.get("group_id"):
        record["group_id"] = data["group_id"]
    result = db.table("menu_addons").insert(record)
    return jsonify(result[0] if isinstance(result, list) else result), 201


@menu_bp.route("/addons/<addon_id>", methods=["PATCH"])
@require_role("admin")
def update_addon(addon_id):
    """
    Update an add-on item (admin only).
    ---
    tags: [Menu]
    parameters:
      - in: path
        name: addon_id
        type: string
        required: true
    responses:
      200:
        description: Add-on updated
    """
    db = get_db()
    data = request.get_json(force=True)
    allowed = {"name", "description", "price", "is_available", "sort_order", "group_id"}
    update = {k: v for k, v in data.items() if k in allowed}
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.table("menu_addons").eq("id", addon_id).update(update)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@menu_bp.route("/addons/<addon_id>/archive", methods=["POST"])
@require_role("admin")
def archive_addon(addon_id):
    """
    Archive an add-on item (admin only).
    ---
    tags: [Menu]
    responses:
      200:
        description: Add-on archived
    """
    db = get_db()
    result = db.table("menu_addons").eq("id", addon_id).update({
        "is_archived": True,
        "is_available": False,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify({"message": MSG.MENU_ADDON_ARCHIVED, "addon": result[0] if isinstance(result, list) else result}), 200


# ─────────────────────────────────────────────────────────────────────────────
# Kitchen Capacity  (daily order cap)
# ─────────────────────────────────────────────────────────────────────────────

@menu_bp.route("/kitchen-capacity", methods=["GET"])
def get_kitchen_capacity():
    """
    Get the kitchen's current daily order capacity and today's order count.
    ---
    tags: [Menu]
    security: []
    responses:
      200:
        description: Kitchen capacity info
    """
    db = get_db()
    capacity, orders_today, at_capacity = _kitchen_stats(db)
    return jsonify({
        "daily_order_capacity": capacity,
        "orders_today": orders_today,
        "is_at_capacity": at_capacity,
    }), 200


@menu_bp.route("/kitchen-capacity", methods=["PATCH"])
@require_role("admin")
def set_kitchen_capacity():
    """
    Set the kitchen's daily order capacity (admin only).
    Pass null to remove the limit entirely.
    ---
    tags: [Menu]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          properties:
            daily_order_capacity:
              type: integer
              description: "Max orders the kitchen will accept today. null = no cap."
    responses:
      200:
        description: Capacity updated
      400:
        description: Invalid value
    """
    db = get_db()
    data = request.get_json(force=True)
    cap = data.get("daily_order_capacity")

    if cap is None:
        db.table("kitchen_settings").eq("key", "daily_order_capacity").update({
            "value": "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": g.user_id,
        })
        return jsonify({"daily_order_capacity": None, "message": MSG.MENU_CAPACITY_LIMIT_REMOVED}), 200

    if not isinstance(cap, int) or cap < 1:
        return jsonify({"error": MSG.MENU_CAPACITY_POSITIVE}), 400

    db.table("kitchen_settings").eq("key", "daily_order_capacity").update({
        "value": str(cap),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": g.user_id,
    })
    _, orders_today, at_capacity = _kitchen_stats(db)
    return jsonify({
        "daily_order_capacity": cap,
        "orders_today": orders_today,
        "is_at_capacity": at_capacity,
    }), 200
