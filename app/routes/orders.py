"""Order routes — create, track, manage delivery."""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role, optional_auth
from app.middleware.rate_limit import rate_limit
from app.services import order_service
from app.services.hp_service import earn_pending_hp
from app.db import get_db
from app.messages import MSG, resolve_msg
from datetime import datetime, timezone

orders_bp = Blueprint("orders", __name__)


def _assigned_rider_contact(db, order: dict) -> dict | None:
    """Resolve the assigned rider from the order's delivery batch.

    The API deliberately returns a tel URI rather than the raw phone number.
    The profile lookup is always keyed by the persisted batch rider_id; there
    is no fallback contact value.
    """
    batch = order.get("delivery_batches")
    if isinstance(batch, list):
        batch = batch[0] if batch else None
    if not isinstance(batch, dict) or not batch.get("rider_id"):
        return None

    profile = (
        db.table("profiles")
        .select("full_name,phone")
        .eq("id", batch["rider_id"])
        .single()
        .execute()
    )
    if not profile:
        return None

    phone = profile.get("phone")
    return {
        "name": profile.get("full_name"),
        "call_link": f"tel:{phone}" if phone else None,
    }


@orders_bp.route("", methods=["POST"])
@optional_auth
@rate_limit("RATE_LIMIT_ORDERS_REQUESTS", "RATE_LIMIT_ORDERS_WINDOW")
def create_order():
    """
    Create a new order. Supports authenticated and guest checkout.
    ---
    tags: [Orders]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [items, payment_method]
          properties:
            items:
              type: array
              items:
                type: object
                properties:
                  menu_item_id:
                    type: string
                  quantity:
                    type: integer
            payment_method:
              type: string
              enum: [wallet, card, split]
            delivery_type:
              type: string
              enum: [on_campus, off_campus]
              description: System decides delivery window; client selects hostel or gate for fee calculation.
            delivery_location_id:
              type: string
              description: Hostel UUID (on_campus) or Gate UUID (off_campus)
            delivery_location_lat:
              type: number
              description: Customer GPS latitude for off-campus distance fee
            delivery_location_lon:
              type: number
              description: Customer GPS longitude for off-campus distance fee
            delivery_address:
              type: object
              description: Optional free-text address snapshot stored for rider notes only
            promo_code:
              type: string
            notes:
              type: string
            squad_name:
              type: string
              description: Name for squad orders
            is_scheduled:
              type: boolean
            scheduled_for_window_id:
              type: string
              description: Explicit future window UUID; system auto-assigns if omitted
            scheduled_date:
              type: string
              format: date
              description: Date hint YYYY-MM-DD for scheduled orders (date only, no time)
            guest_name:
              type: string
            guest_phone:
              type: string
            guest_email:
              type: string
    responses:
      201:
        description: Order created
      400:
        description: Validation error
    """
    data = request.get_json(force=True)
    user_id = g.user_id

    if not data.get("items"):
        return jsonify({"error": MSG.ORDER_ITEMS_REQUIRED}), 400
    if not data.get("payment_method"):
        return jsonify({"error": MSG.ORDER_PAYMENT_METHOD_REQUIRED}), 400
    # delivery_address is now optional — delivery fees are calculated from
    # delivery_type + delivery_location_id (hostel/gate). The free-text address
    # is stored as a snapshot for rider notes only.

    is_guest = user_id is None
    if is_guest:
        for field in ["guest_name", "guest_phone"]:
            if not data.get(field):
                return jsonify({"error": f"'{field}' required for guest checkout"}), 400
        if data.get("payment_method") == "wallet":
            return jsonify({"error": MSG.ORDER_WALLET_LOGIN_REQUIRED}), 400
    try:
        order = order_service.create_order(user_id, data)
        return jsonify(order), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": MSG.ORDER_CREATE_FAILED, "detail": str(e)}), 500


@orders_bp.route("", methods=["GET"])
@require_auth
def list_orders():
    """
    List authenticated user's orders.
    ---
    tags: [Orders]
    parameters:
      - in: query
        name: status
        type: string
      - in: query
        name: limit
        type: integer
        default: 20
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: Order list
    """
    db = get_db()
    q = db.table("orders").select("*,order_items(*)").eq("user_id", g.user_id)
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    orders = q.order("created_at", ascending=False).limit(limit).offset(offset).execute()
    return jsonify(orders), 200


@orders_bp.route("/<order_id>", methods=["GET"])
@optional_auth
def get_order(order_id):
    """
    Get order detail. Authenticated users can only see their own orders.
    Guest orders accessible via claim_token query param.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: query
        name: claim_token
        type: string
    responses:
      200:
        description: Order detail
      403:
        description: Access denied
      404:
        description: Not found
    """
    import uuid as _uuid
    try:
        _uuid.UUID(order_id)
    except ValueError:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    db = get_db()
    order = db.table("orders").select("*,order_items(*),delivery_windows(*),delivery_batches(rider_id,zone,status)").eq("id", order_id).single().execute()
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    claim_token = request.args.get("claim_token")
    if g.user_id:
        if order.get("user_id") and order["user_id"] != g.user_id:
            return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403
    elif claim_token:
        if order.get("claim_token") != claim_token:
            return jsonify({"error": MSG.ORDER_INVALID_CLAIM}), 403
    else:
        return jsonify({"error": MSG.ORDER_AUTH_REQUIRED}), 403

    # Resolve the assigned rider from the persisted batch/profile relation.
    # No phone number is embedded in the response or codebase.
    if g.user_id:
        rider = _assigned_rider_contact(db, order)
        if rider:
            order["assigned_rider"] = rider

    return jsonify(order), 200


@orders_bp.route("/<order_id>/call-rider", methods=["GET"])
@require_auth
def call_assigned_rider(order_id):
    """Return a dynamic call link for the rider assigned to the order."""
    import uuid as _uuid

    try:
        _uuid.UUID(order_id)
    except (ValueError, AttributeError):
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    db = get_db()
    order = (
        db.table("orders")
        .select("id,user_id,delivery_batches(rider_id,status)")
        .eq("id", order_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    if order.get("user_id") != g.user_id:
        return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403

    rider = _assigned_rider_contact(db, order)
    if rider is None:
        return jsonify({"error": MSG.RIDER_NOT_ASSIGNED}), 404
    if rider.get("call_link") is None:
        return jsonify({"error": MSG.RIDER_NO_PHONE}), 404

    return jsonify({"rider": rider}), 200


@orders_bp.route("/<order_id>/status", methods=["PATCH"])
@require_role("admin", "kitchen", "rider")
def update_status(order_id):
    """
    Update order status (kitchen/rider/admin).
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [status]
          properties:
            status: {type: string}
            notes: {type: string}
    responses:
      200:
        description: Status updated
      400:
        description: Invalid transition
    """
    data = request.get_json(force=True) or {}
    new_status = data.get("status")
    if not new_status:
        return jsonify({"error": MSG.ORDER_STATUS_REQUIRED}), 400

    try:
        result = order_service.update_order_status(
            order_id=order_id,
            new_status=new_status,
            changed_by=g.user_id,
            notes=data.get("notes", ""),
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@orders_bp.route("/<order_id>/walk", methods=["POST"])
@require_role("admin", "kitchen", "rider")
def walk_order_status(order_id):
    """
    Walk an order through all intermediate states to reach a target status in
    one request. The server resolves the shortest legal path through the state
    machine automatically (e.g. received → preparing → ready → assigned →
    out_for_delivery → delivered).

    Useful for kitchen staff who want to skip straight to 'delivered' without
    making five sequential PATCH calls.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [target_status]
          properties:
            target_status:
              type: string
              example: delivered
            notes:
              type: string
    responses:
      200:
        description: Order walked to target status
        schema:
          properties:
            steps:
              type: array
              items: {type: string}
              example: [preparing, ready, assigned, out_for_delivery, delivered]
            final:
              type: object
      400:
        description: Invalid target or no path exists
    """
    data = request.get_json(force=True) or {}
    target_status = data.get("target_status")
    if not target_status:
        return jsonify({"error": MSG.ORDER_TARGET_STATUS_REQUIRED}), 400

    try:
        result = order_service.walk_order_to_status(
            order_id=order_id,
            target_status=target_status,
            changed_by=g.user_id,
            notes=data.get("notes", ""),
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@orders_bp.route("/<order_id>/review", methods=["POST"])
@require_auth
def submit_review(order_id):
    """
    Submit an order review with optional kitchen and rider star ratings (earns HP on every review).
    Feeds into kitchen/rider performance reports via kitchen_rating and rider_rating fields.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [rating]
          properties:
            rating:         {type: integer, enum: [1,2,3,4,5], description: "Overall order rating"}
            kitchen_rating: {type: integer, enum: [1,2,3,4,5], description: "Food quality / preparation (optional)"}
            rider_rating:   {type: integer, enum: [1,2,3,4,5], description: "Delivery speed / professionalism (optional)"}
            comment:        {type: string}
    responses:
      201:
        description: Review submitted, HP earned
      400:
        description: Already reviewed or order not yet delivered
    """
    db = get_db()
    data = request.get_json(force=True)

    order = db.table("orders").select("user_id,status").eq("id", order_id).single().execute()
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    if order.get("user_id") != g.user_id:
        return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403
    if order.get("status") != "delivered":
        return jsonify({"error": MSG.ORDER_REVIEW_DELIVERED_ONLY}), 400

    existing_review = (
        db.table("order_reviews")
        .select("id")
        .eq("order_id", order_id)
        .eq("user_id", g.user_id)
        .execute()
    )
    if existing_review:
        return jsonify({"error": MSG.ORDER_ALREADY_REVIEWED}), 400

    def _clamp_rating(val):
        """Parse and clamp a rating value to 1–5, or return None if not provided."""
        if val is None:
            return None
        try:
            return max(1, min(5, int(val)))
        except (TypeError, ValueError):
            return None

    # Build review payload — kitchen_rating and rider_rating are optional columns
    # added in migration 16. Included only when the caller provides them so that
    # a missing column never causes an insert failure before the migration runs.
    from app.db import SupabaseError as _SupabaseError
    review_payload = {
        "order_id": order_id,
        "user_id": g.user_id,
        "rating": max(1, min(5, int(data.get("rating", 5)))),
        "comment": data.get("comment", ""),
        "hp_awarded": 0,
        "kitchen_rating": _clamp_rating(data.get("kitchen_rating")),
        "rider_rating":   _clamp_rating(data.get("rider_rating")),
    }

    try:
        review = db.table("order_reviews").insert(review_payload)
    except _SupabaseError as e:
        # Only fall back if the error is specifically about missing columns.
        # Re-raise anything else so real DB errors are not silently swallowed.
        err_text = (str(e) + str(getattr(e, "details", ""))).lower()
        if "column" not in err_text or "does not exist" not in err_text:
            raise
        fallback = {k: v for k, v in review_payload.items()
                    if k not in ("kitchen_rating", "rider_rating")}
        review = db.table("order_reviews").insert(fallback)

    review_row = review[0] if isinstance(review, list) else review
    review_id = review_row["id"]

    hp_amount = current_app.config["REVIEW_HP"]
    earn_pending_hp(
        user_id=g.user_id,
        amount=hp_amount,
        source_type="review",
        reference_id=review_id,
        notes="HP for leaving a review",
    )
    db.table("order_reviews").eq("id", review_id).update({"hp_awarded": hp_amount})

    return jsonify({"review": review_row, "hp_awarded": hp_amount}), 201


@orders_bp.route("/<order_id>/claim", methods=["POST"])
@require_auth
def claim_guest_order(order_id):
    """
    Link a guest order to a newly created account.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [claim_token]
          properties:
            claim_token: {type: string}
    responses:
      200:
        description: Order linked to account
    """
    data = request.get_json(force=True) or {}
    claim_token = data.get("claim_token")
    if not claim_token:
        return jsonify({"error": MSG.ORDER_CLAIM_TOKEN_REQUIRED}), 400

    try:
        result = get_db().rpc("claim_guest_order", {
            "p_order_id": order_id,
            "p_user_id": g.user_id,
            "p_claim_token": claim_token,
        })
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@orders_bp.route("/<order_id>/refund", methods=["POST"])
@require_role("admin")
def refund_order(order_id):
    """
    Initiate a refund for an order (admin only).
    Transitions the order to 'refunded' status and credits the wallet or logs the refund.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [reason]
          properties:
            reason: {type: string, description: "Reason for the refund"}
            refund_amount: {type: number, description: "Partial refund amount in Naira. Defaults to full order amount."}
            refund_to_wallet: {type: boolean, default: true, description: "If true, credit the wallet. If false, log as manual refund."}
    responses:
      200:
        description: Refund processed
      400:
        description: Invalid state or amount
      404:
        description: Order not found
    """
    data = request.get_json(force=True) or {}
    reason = data.get("reason", "").strip()
    if not reason:
        return jsonify({"error": MSG.ORDER_REFUND_REASON_REQUIRED}), 400

    db = get_db()
    order = db.table("orders").select("id,status,total_amount,user_id,payment_status,wallet_amount_used,card_amount_used").eq("id", order_id).single().execute()
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    non_refundable = {"refunded", "cancelled"}
    if order.get("status") in non_refundable:
        return jsonify({"error": MSG.ORDER_ALREADY_STATUS.format(status=order["status"])}), 400

    total_amount = float(order.get("total_amount", 0))
    refund_amount = float(data.get("refund_amount", total_amount))
    if refund_amount <= 0 or refund_amount > total_amount:
        return jsonify({"error": MSG.ORDER_REFUND_AMOUNT_INVALID.format(max=total_amount)}), 400

    refund_to_wallet = bool(data.get("refund_to_wallet", True))

    from app.services import order_service
    try:
        order_service.update_order_status(
            order_id=order_id,
            new_status="refunded",
            changed_by=g.user_id,
            notes=f"Refund: {reason}",
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    db.table("orders").eq("id", order_id).update({
        "notes": f"[REFUNDED by {g.user_id[:8]}] {reason}",
        "refunded_at": datetime.now(timezone.utc).isoformat(),
    })

    wallet_credited = False
    if refund_to_wallet and order.get("user_id"):
        try:
            from app.services.wallet_service import credit_wallet
            credit_wallet(
                user_id=order["user_id"],
                amount=refund_amount,
                payment_reference=f"REFUND-{order_id[:8].upper()}",
                reference_id=order_id,
                reference_type="refund",
                notes=f"Refund for order #{order_id[:8].upper()}: {reason}",
            )
            wallet_credited = True
        except Exception as exc:
            wallet_credited = False

    from app.services.notification_service import send_notification
    if order.get("user_id"):
        try:
            send_notification(
                user_id=order["user_id"],
                notif_type="order_refunded",
                title=MSG.ORDER_REFUND_TITLE,
                body=(
                    MSG.ORDER_REFUND_BODY_WALLET.format(amount=f"{refund_amount:.0f}", reason=reason)
                    if wallet_credited
                    else MSG.ORDER_REFUND_BODY_OTHER.format(amount=f"{refund_amount:.0f}", reason=reason)
                ),
                reference_id=order_id,
                reference_type="order",
                channels=["push", "in_app", "email"],
            )
        except Exception:
            pass

    return jsonify({
        "message": MSG.ORDER_REFUND_SUCCESS,
        "order_id": order_id,
        "status": "refunded",
        "refund_amount": refund_amount,
        "reason": reason,
        "wallet_credited": wallet_credited,
    }), 200


@orders_bp.route("/scheduled", methods=["GET"])
@require_auth
def list_scheduled_orders():
    """
    List the authenticated user's upcoming scheduled orders.

    Returns orders placed with is_scheduled=True that are still in 'received'
    status (i.e. not yet promoted to preparing). Sorted by scheduled_for
    ascending so the soonest order appears first.
    ---
    tags: [Orders]
    parameters:
      - in: query
        name: limit
        type: integer
        default: 20
      - in: query
        name: offset
        type: integer
        default: 0
    responses:
      200:
        description: User's pending scheduled orders
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))
    orders = (
        db.table("orders")
        .select("*,order_items(name_snapshot,quantity,price_snapshot,line_total),"
                "delivery_windows(label,starts_at,ends_at)")
        .eq("user_id", g.user_id)
        .eq("is_scheduled", "true")
        .eq("status", "received")
        .order("scheduled_for", ascending=True)
        .limit(limit)
        .offset(offset)
        .execute()
    ) or []
    return jsonify({"scheduled_orders": orders, "count": len(orders)}), 200


@orders_bp.route("/<order_id>/scheduled", methods=["DELETE"])
@require_auth
def cancel_scheduled_order(order_id):
    """
    Cancel a scheduled order before it is due for preparation.

    Only the order owner can cancel, and only while the order is still
    pending (is_scheduled=True, status='received'). If the order was paid
    via wallet, the amount is refunded back to the wallet.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            reason: {type: string}
    responses:
      200:
        description: Scheduled order cancelled
      403:
        description: Not the order owner
      409:
        description: Order is not a pending scheduled order
      404:
        description: Order not found
    """
    db = get_db()
    order = (
        db.table("orders")
        .select("id,user_id,status,is_scheduled,total_amount,wallet_amount_used,hp_redeemed,payment_status")
        .eq("id", order_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    if order.get("user_id") != g.user_id:
        return jsonify({"error": MSG.ORDER_CANCEL_NOT_OWNER}), 403
    is_scheduled = order.get("is_scheduled") in (True, "true", "t")
    if not is_scheduled or order.get("status") != "received":
        return jsonify({"error": MSG.ORDER_NOT_SCHEDULED_PENDING}), 409

    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "Scheduled order cancelled by customer")

    try:
        order_service.update_order_status(order_id, "cancelled", g.user_id, reason)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    wallet_refunded = 0.0
    wallet_amount_used = float(order.get("wallet_amount_used") or 0)
    if wallet_amount_used > 0:
        from app.services.wallet_service import credit_wallet
        credit_wallet(
            user_id=g.user_id,
            amount=wallet_amount_used,
            payment_reference=f"scheduled-cancel-{order_id[:8].upper()}",
            reference_id=order_id,
            reference_type="refund",
            notes=f"Refund for cancelled scheduled order #{order_id[:8].upper()}",
        )
        wallet_refunded = wallet_amount_used

    hp_refunded = 0
    hp_redeemed = int(order.get("hp_redeemed") or 0)
    if hp_redeemed > 0 and order.get("payment_status") == "paid":
        try:
            from app.services.hp_service import award_active_hp
            award_active_hp(
                user_id=g.user_id,
                amount=hp_redeemed,
                txn_type="earn_order",
                reference_id=order_id,
                reference_type="order_cancel_hp_refund",
                source_type="order",
                notes=f"HP refund for cancelled scheduled order #{order_id[:8].upper()}",
            )
            hp_refunded = hp_redeemed
        except Exception:
            pass

    return jsonify({
        "message": MSG.ORDER_CANCELLED_OK,
        "order_id": order_id,
        "status": "cancelled",
        "wallet_refunded": wallet_refunded,
        "hp_refunded": hp_refunded,
    }), 200


@orders_bp.route("/active", methods=["GET"])
@require_auth
def active_order():
    """
    Get the authenticated user's current active (in-progress) order, if any.
    ---
    tags: [Orders]
    responses:
      200:
        description: Active order or null
    """
    db = get_db()
    TERMINAL = ["delivered", "cancelled", "refunded"]
    rows = (
        db.table("orders")
        .select("*,order_items(id,menu_item_id,name_snapshot,quantity,price_snapshot,line_total)")
        .eq("user_id", g.user_id)
        .not_.in_("status", TERMINAL)
        .order("created_at", ascending=False)
        .limit(1)
        .execute()
    )
    order = rows[0] if rows else None
    return jsonify({"order": order}), 200


@orders_bp.route("/delivery-windows", methods=["GET"])
def list_delivery_windows():
    """
    List upcoming open delivery windows available for ordering.
    ---
    tags: [Orders]
    security: []
    responses:
      200:
        description: Available delivery windows
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    windows = (
        db.table("delivery_windows")
        .select("*")
        .gte("ends_at", now)
        .eq("status", "open")
        .order("starts_at")
        .execute()
    ) or []
    return jsonify(windows), 200


@orders_bp.route("/delivery-windows/status", methods=["GET"])
def delivery_windows_status():
    """
    Return whether the kitchen is currently open and list available delivery
    windows for scheduling. Used by the frontend to decide whether to show
    the normal checkout or the "Schedule Your Order" popup.
    ---
    tags: [Orders]
    security: []
    responses:
      200:
        description: |
          {
            is_open: bool,
            can_schedule: bool,
            available_windows: [...],
            next_window: {...} | null
          }
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # ── 1. Determine if the kitchen is currently open ─────────────────────────
    from datetime import time as _time, date as _date

    def _parse_t(t_str: str) -> _time:
        try:
            parts = str(t_str).split(":")
            return _time(int(parts[0]), int(parts[1]))
        except Exception:
            return _time(0, 0)

    today_iso = _date.today().isoformat()
    override_rows = (
        db.table("operating_hour_overrides")
        .select("*")
        .eq("date", today_iso)
        .execute()
    ) or []
    override = override_rows[0] if override_rows else None

    hours = db.table("operating_hours").select("*").order("weekday").execute() or []

    is_open = False
    today_weekday = now.weekday()

    if override:
        if override.get("is_closed"):
            is_open = False
        else:
            open_val = override.get("open_time") or override.get("opens_at")
            close_val = override.get("close_time") or override.get("closes_at")
            if open_val and close_val:
                is_open = _parse_t(open_val) <= now.time() <= _parse_t(close_val)
            else:
                # Override says open but no specific hours — treat as open all day
                is_open = True
    else:
        for row in hours:
            if row.get("weekday") == today_weekday:
                if row.get("is_closed"):
                    is_open = False
                else:
                    open_val = row.get("open_time") or row.get("opens_at", "00:00")
                    close_val = row.get("close_time") or row.get("closes_at", "23:59")
                    is_open = _parse_t(open_val) <= now.time() <= _parse_t(close_val)
                break

    # ── 2. Fetch upcoming open windows for scheduling ─────────────────────────
    windows = (
        db.table("delivery_windows")
        .select("*")
        .gte("ends_at", now_iso)
        .eq("status", "open")
        .order("starts_at")
        .execute()
    ) or []

    next_window = windows[0] if windows else None

    next_window_starts_at = next_window.get("starts_at") if next_window else None

    return jsonify({
        "is_open": is_open,
        "can_schedule": len(windows) > 0,
        "available_windows": windows,
        "next_window": next_window,
        "next_window_starts_at": next_window_starts_at,
    }), 200


@orders_bp.route("/delivery-zones", methods=["GET"])
def list_delivery_zones():
    """
    List delivery zones with fees and estimated delivery times.
    ---
    tags: [Orders]
    security: []
    responses:
      200:
        description: Delivery zones
    """
    db = get_db()
    zones = (
        db.table("delivery_zones")
        .select("*")
        .eq("is_active", "true")
        .order("name")
        .execute()
    ) or []
    return jsonify(zones), 200


@orders_bp.route("/validate-promo", methods=["POST"])
@optional_auth
def validate_promo():
    """
    Validate a promo code against an order subtotal without applying it.
    Thin wrapper around the same promo logic used at checkout, so
    discount previews shown pre-checkout always match what create_order applies.
    ---
    tags: [Orders]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [code, order_subtotal]
          properties:
            code: {type: string}
            order_subtotal: {type: number}
    responses:
      200:
        description: Promo code valid with discount info
      400:
        description: Invalid, expired, or inapplicable code
    """
    data = request.get_json(force=True) or {}
    code = (data.get("code") or "").strip()
    try:
        subtotal = float(data.get("order_subtotal", 0))
    except (TypeError, ValueError):
        return jsonify({"error": MSG.ERR_BAD_REQUEST}), 400

    if not code:
        return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field="code")}), 400

    try:
        result = order_service._apply_promo(getattr(g, "user_id", None), code, subtotal)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify({
        "valid": True,
        "code": code.upper(),
        "calculated_discount": result["discount"],
        "promo_code_id": result["promo_code_id"],
    }), 200


@orders_bp.route("/<order_id>/cancel", methods=["POST"])
@require_auth
def cancel_order(order_id):
    """
    Cancel an order. Only the order owner can cancel, and only while status is 'received'.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            reason: {type: string}
    responses:
      200:
        description: Order cancelled
      403:
        description: Not the order owner
      409:
        description: Order cannot be cancelled at this stage
      404:
        description: Order not found
    """
    db = get_db()
    order = (
        db.table("orders")
        .select("id,user_id,status,total_amount,wallet_amount_used,card_amount_used,hp_redeemed,payment_status")
        .eq("id", order_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    if order.get("user_id") != g.user_id:
        return jsonify({"error": MSG.ORDER_CANCEL_NOT_OWNER}), 403
    # Only "received" orders can be cancelled by the customer (kitchen hasn't started yet).
    # "received" means no kitchen work has begun, so cancellation is always safe regardless
    # of time-of-day — the ordering-window check has been intentionally removed here.
    if order.get("status") != "received":
        return jsonify({"error": MSG.ORDER_CANCEL_WRONG_STATUS}), 409

    data = request.get_json(force=True, silent=True) or {}
    reason = data.get("reason", "Cancelled by customer")

    try:
        order_service.update_order_status(order_id, "cancelled", g.user_id, reason)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    # ── Refund: wallet→wallet, card→wallet, HP→HP ────────────────────────────
    wallet_refunded = 0.0
    hp_refunded = 0
    wallet_amount = float(order.get("wallet_amount_used") or 0)
    card_amount = float(order.get("card_amount_used") or 0)
    hp_redeemed = int(order.get("hp_redeemed") or 0)

    if wallet_amount > 0:
        try:
            from app.services.wallet_service import credit_wallet
            credit_wallet(
                user_id=g.user_id,
                amount=wallet_amount,
                payment_reference=f"cancel-{order_id[:8].upper()}",
                reference_id=order_id,
                reference_type="refund",
                notes=f"Refund for cancelled order #{order_id[:8].upper()}",
            )
            wallet_refunded += wallet_amount
        except Exception:
            pass

    if card_amount > 0:
        # Card payments refund to wallet
        try:
            from app.services.wallet_service import credit_wallet
            credit_wallet(
                user_id=g.user_id,
                amount=card_amount,
                payment_reference=f"cancel-card-{order_id[:8].upper()}",
                reference_id=order_id,
                reference_type="refund",
                notes=f"Card refund to wallet for cancelled order #{order_id[:8].upper()}",
            )
            wallet_refunded += card_amount
        except Exception:
            pass

    if hp_redeemed > 0 and order.get("payment_status") == "paid":
        # Restore redeemed HP
        try:
            from app.services.hp_service import award_active_hp
            award_active_hp(
                user_id=g.user_id,
                amount=hp_redeemed,
                txn_type="earn_order",
                reference_id=order_id,
                reference_type="order_cancel_hp_refund",
                source_type="order",
                notes=f"HP refund for cancelled order #{order_id[:8].upper()}",
            )
            hp_refunded = hp_redeemed
        except Exception:
            pass

    from app.services.notification_service import send_notification
    try:
        send_notification(
            user_id=g.user_id,
            notif_type="order_refunded",
            title=MSG.ORDER_REFUND_TITLE,
            body=MSG.ORDER_REFUND_BODY_WALLET.format(
                amount=f"{wallet_refunded:.0f}", reason=reason
            ) if wallet_refunded > 0 else MSG.ORDER_CANCELLED_BODY,
            reference_id=order_id,
            reference_type="order",
            channels=["push", "in_app", "email"],
        )
    except Exception:
        pass

    return jsonify({
        "message": MSG.ORDER_CANCELLED_OK,
        "order_id": order_id,
        "status": "cancelled",
        "wallet_refunded": wallet_refunded,
        "hp_refunded": hp_refunded,
    }), 200


@orders_bp.route("/<order_id>/reorder", methods=["POST"])
@require_auth
def reorder(order_id):
    """
    Fetch items from a past order to pre-populate a new order (reorder helper).
    Returns items with current menu prices — does not create an order.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
    responses:
      200:
        description: Reorder item list with current prices
      403:
        description: Not the order owner
      404:
        description: Order not found
    """
    import uuid as _uuid
    try:
        _uuid.UUID(order_id)
    except (ValueError, AttributeError):
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    db = get_db()
    order = (
        db.table("orders")
        .select("id,user_id")
        .eq("id", order_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404
    if order.get("user_id") != g.user_id:
        return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403

    past_items = (
        db.table("order_items")
        .select("menu_item_id,name_snapshot,quantity,price_snapshot")
        .eq("order_id", order_id)
        .execute()
    ) or []

    enriched = []
    for item in past_items:
        current_price = item.get("price_snapshot")
        is_available = False
        try:
            menu = (
                db.table("menu_items")
                .select("price,is_available,name")
                .eq("id", item["menu_item_id"])
                .is_("deleted_at", "null")
                .single()
                .execute()
            )
            if menu:
                current_price = float(menu.get("price", current_price))
                is_available = bool(menu.get("is_available", False))
        except Exception:
            pass

        enriched.append({
            "menu_item_id": item["menu_item_id"],
            "name": item.get("name_snapshot"),
            "quantity": item.get("quantity", 1),
            "current_price": current_price,
            "is_available": is_available,
        })

    return jsonify({"message": MSG.ORDER_REORDER_ITEMS, "items": enriched, "original_order_id": order_id}), 200


@orders_bp.route("/<order_id>/share", methods=["POST"])
@require_auth
def record_order_share(order_id):
    """
    Record that the user shared their order confirmation (e.g. on WhatsApp).
    Awards 25 HP (pending) — max once per day across all orders.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            platform: {type: string, description: "Share platform. Default: whatsapp"}
    responses:
      200:
        description: Share recorded and HP awarded (or already claimed today)
      404:
        description: Order not found
    """
    db = get_db()
    order = (
        db.table("orders")
        .select("id,user_id,status")
        .eq("id", order_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.SHARE_PROMPT_ORDER_NOT_FOUND}), 404

    from datetime import timedelta
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    already_today = (
        db.table("order_share_events")
        .select("id")
        .eq("user_id", g.user_id)
        .gte("created_at", today_start)
        .limit(1)
        .execute()
    )
    if already_today:
        return jsonify({"message": MSG.SHARE_PROMPT_ALREADY_TODAY, "hp_awarded": 0}), 200

    hp_to_award = current_app.config.get("SHARE_PROMPT_HP", 25)

    from app.services.streak_service import check_monthly_cap, update_monthly_tracker
    cap_check = check_monthly_cap(g.user_id, hp_to_award)
    actual_hp = cap_check["capped_amount"] if cap_check["allowed"] else 0

    now = datetime.now(timezone.utc).isoformat()
    platform = (request.get_json(force=True) or {}).get("platform", "whatsapp")

    db.table("order_share_events").insert({
        "user_id": g.user_id,
        "order_id": order_id,
        "platform": platform,
        "hp_awarded": actual_hp,
        "created_at": now,
    })

    if actual_hp > 0:
        from app.services.hp_service import earn_pending_hp
        earn_pending_hp(
            user_id=g.user_id,
            amount=actual_hp,
            source_type="social",
            reference_id=order_id,
            notes=f"Order share on {platform} — {actual_hp} HP pending",
        )
        update_monthly_tracker(g.user_id, actual_hp)

    return jsonify({
        "message": resolve_msg(MSG.SHARE_PROMPT_HP_TITLE, hp=actual_hp) if actual_hp else MSG.SHARE_PROMPT_ALREADY_TODAY,
        "hp_awarded": actual_hp,
        "platform": platform,
    }), 200


@orders_bp.route("/<order_id>/squad-members", methods=["POST"])
@require_auth
def add_squad_members(order_id):
    """
    Add squad members to a squad order for HP splitting.
    Non-registered emails receive an auto-invite for referral attribution.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [emails]
          properties:
            emails:
              type: array
              items: {type: string}
              description: Email addresses of squad participants
            split_hp:
              type: boolean
              description: Whether to split HP with squad. Default true.
    responses:
      200:
        description: Squad members recorded, HP split queued
      400:
        description: Validation error
      404:
        description: Order not found or not yours
    """
    db = get_db()
    order = (
        db.table("orders")
        .select("id,user_id,status,hp_earned")
        .eq("id", order_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    data = request.get_json(force=True) or {}
    emails = [e.strip().lower() for e in (data.get("emails") or []) if e and e.strip()]
    if not emails:
        return jsonify({"error": "At least one email is required"}), 400

    split_hp = data.get("split_hp", True)
    organizer_profile = (
        db.table("profiles").select("full_name,email").eq("id", g.user_id).single().execute()
    ) or {}
    organizer_name = organizer_profile.get("full_name") or "Someone"
    frontend_url = current_app.config.get("FRONTEND_URL", "")

    from app.services.notification_service import send_notification
    results = []
    now = datetime.now(timezone.utc).isoformat()

    for email in emails:
        existing_member = (
            db.table("squad_members")
            .select("id")
            .eq("order_id", order_id)
            .eq("email", email)
            .single()
            .execute()
        )
        if existing_member:
            results.append({"email": email, "status": "already_added"})
            continue

        profile = (
            db.table("profiles").select("id,full_name").eq("email", email).single().execute()
        )
        member_payload = {
            "order_id": order_id,
            "email": email,
            "hp_share": 0,
            "invite_sent": False,
            "is_registered": bool(profile),
            "referral_attributed": False,
            "created_at": now,
        }
        if profile:
            member_payload["user_id"] = profile["id"]

        try:
            db.table("squad_members").insert(member_payload)
        except Exception:
            results.append({"email": email, "status": "error"})
            continue

        if not profile:
            # Send auto-invite for referral vector
            ref_code = organizer_profile.get("referral_code", "")
            invite_link = f"{frontend_url}/register?ref={ref_code}&email={email}" if ref_code else f"{frontend_url}/register"
            try:
                from app.utils.email import send_email
                send_email(
                    to_email=email,
                    to_name="",
                    template_key="squad_invite",
                    data={
                        "organizer": organizer_name,
                        "invite_link": invite_link,
                    },
                )
                db.table("squad_members").eq("order_id", order_id).eq("email", email).update({"invite_sent": True})
            except Exception:
                pass
            results.append({"email": email, "status": "invited"})
        else:
            # Notify registered user
            try:
                send_notification(
                    user_id=profile["id"],
                    notif_type="squad_order",
                    template_data={"organizer": organizer_name},
                )
            except Exception:
                pass
            results.append({"email": email, "status": "notified"})

    # If order is already delivered and split_hp is enabled, distribute HP now
    if split_hp and order.get("status") == "delivered" and order.get("hp_earned", 0) > 0:
        _distribute_squad_hp(order_id, order["hp_earned"], g.user_id)

    return jsonify({"message": "Squad members recorded", "results": results}), 200


def _distribute_squad_hp(order_id: str, total_hp: int, organizer_id: str):
    """Split HP evenly among registered squad members + organizer."""
    if total_hp <= 0:
        return
    db = get_db()
    try:
        members = (
            db.table("squad_members")
            .select("id,user_id,email,is_registered")
            .eq("order_id", order_id)
            .eq("is_registered", "true")
            .execute()
        ) or []

        registered_ids = [m["user_id"] for m in members if m.get("user_id")]
        if organizer_id not in registered_ids:
            registered_ids.insert(0, organizer_id)

        if not registered_ids:
            return

        share = max(1, total_hp // len(registered_ids))
        from app.services.hp_service import earn_pending_hp

        for uid in registered_ids:
            try:
                earn_pending_hp(
                    user_id=uid,
                    amount=share,
                    source_type="squad_bonus",
                    reference_id=order_id,
                    notes=f"Squad HP split — {share} HP from order {order_id[:8]}",
                )
            except Exception:
                pass

        # Record hp_share on squad_members rows
        for m in members:
            if m.get("user_id") in registered_ids:
                try:
                    db.table("squad_members").eq("id", m["id"]).update({"hp_share": share})
                except Exception:
                    pass
    except Exception as e:
        pass


@orders_bp.route("/<order_id>/history", methods=["GET"])
@require_auth
def order_status_history(order_id):
    """
    Get the full status change history for an order.
    ---
    tags: [Orders]
    parameters:
      - in: path
        name: order_id
        type: string
        required: true
    responses:
      200:
        description: List of status transitions with timestamps and actor info
      404:
        description: Order not found or not accessible
    """
    import uuid as _uuid
    try:
        _uuid.UUID(order_id)
    except (ValueError, AttributeError):
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    from app.middleware.auth import require_role as _rr
    db = get_db()
    order = (
        db.table("orders")
        .select("id,user_id,guest_phone")
        .eq("id", order_id)
        .single()
        .execute()
    )
    if not order:
        return jsonify({"error": MSG.ORDER_NOT_FOUND}), 404

    is_owner = (
        order.get("user_id") == g.user_id or
        getattr(g, "user_role", None) in ("admin", "kitchen", "rider")
    )
    if not is_owner:
        return jsonify({"error": MSG.ORDER_ACCESS_DENIED}), 403

    history = (
        db.table("order_status_logs")
        .select("*")
        .eq("order_id", order_id)
        .order("created_at", ascending=True)
        .execute()
    )
    return jsonify(history), 200
