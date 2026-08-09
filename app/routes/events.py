"""Events routes — discovery, catering requests, QR check-in, ticket tiers, admin export."""

from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_auth, require_role
from app.services.hp_service import earn_pending_hp
from app.db import get_db, SupabaseError
from app.messages import MSG, resolve_msg
from app.utils.validators import (
    validate_choice, validate_non_negative_number, validate_uuid,
    validate_datetime_order, sanitize_string,
)
from datetime import datetime, timezone
import uuid

events_bp = Blueprint("events", __name__)

CATERING_STATUSES = ("new", "reviewed", "quoted", "accepted", "completed", "rejected", "cancelled")


@events_bp.route("", methods=["GET"])
def list_events():
    """
    List active upcoming events.
    ---
    tags: [Events]
    security: []
    responses:
      200:
        description: Event list
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    events = (
        db.table("events")
        .select("id,title,slug,description,location,starts_at,ends_at,hp_reward,hp_promo_enabled,is_featured")
        .eq("is_published", "true")
        .gte("starts_at", now)
        .order("starts_at")
        .execute()
    )
    return jsonify(events or []), 200


@events_bp.route("/<event_id>", methods=["GET"])
def get_event(event_id):
    """
    Get event detail.
    ---
    tags: [Events]
    security: []
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
    responses:
      200:
        description: Event detail
      404:
        description: Not found
    """
    db = get_db()
    event = db.table("events").select("*").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    try:
        tickets = db.table("event_tickets").select("id").eq("event_id", event_id).execute()
        ticket_ids = [t["id"] for t in (tickets or [])]
        if ticket_ids:
            checkins = db.table("event_checkins").select("id").in_("ticket_id", ticket_ids).execute()
            event["checkin_count"] = len(checkins or [])
        else:
            event["checkin_count"] = 0
    except Exception:
        event["checkin_count"] = 0
    return jsonify(event), 200


@events_bp.route("/<event_id>/checkin", methods=["POST"])
@require_auth
def checkin(event_id):
    """
    Check in to a Holy Grills event using QR token. Awards HP to pending pool.
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [qr_token]
          properties:
            qr_token: {type: string}
    responses:
      200:
        description: Check-in successful, HP awarded
      400:
        description: Already checked in or invalid QR
    """
    db = get_db()
    data = request.get_json(force=True)
    qr_token = data.get("qr_token", "").strip()

    try:
        # Try the atomic RPC first (validates ticket UUID, prevents double check-in,
        # inserts event_checkins row — all in one transaction).
        # Falls back to direct DB operations if the RPC is not yet in the
        # PostgREST schema cache (PGRST202) — see migrations/schema.sql section 5.
        try:
            result = db.rpc("checkin_event_atomic", {
                "p_event_id": event_id,
                "p_user_id": g.user_id,
                "p_qr_token": qr_token,
            })
            if isinstance(result, dict) and result.get("error"):
                return jsonify({"error": result["error"]}), 400
        except SupabaseError as rpc_err:
            _rpc_err_str = str(rpc_err)
            _is_missing_fn = "PGRST202" in _rpc_err_str or "Could not find the function" in _rpc_err_str
            # 42703 = undefined_column — the deployed checkin_event_atomic() function is
            # out of sync with the live event_checkins schema (expects checked_in_at,
            # but the table has checked_in_by). Fall back to the direct-DB path below
            # until the DB function is redefined to match the live schema.
            _is_schema_drift = "42703" in _rpc_err_str or "does not exist" in _rpc_err_str
            if not _is_missing_fn and not _is_schema_drift:
                raise
            # ── Fallback: direct DB check-in (mirrors the RPC logic) ─────────
            # Use limit(1) not .single() so duplicate legacy ticket rows don't
            # cause a query failure — matches the RPC's LIMIT 1 behaviour.
            tickets_rows = (
                db.table("event_tickets")
                .select("id")
                .eq("event_id", event_id)
                .eq("user_id", g.user_id)
                .limit(1)
                .execute()
            )
            if not tickets_rows:
                return jsonify({"error": MSG.EVENT_NO_TICKET}), 400
            ticket_id_str = tickets_rows[0]["id"]
            if ticket_id_str != qr_token:
                return jsonify({"error": MSG.EVENT_INVALID_QR}), 400
            existing_checkin = (
                db.table("event_checkins")
                .select("id")
                .eq("ticket_id", ticket_id_str)
                .execute()
            )
            if existing_checkin:
                return jsonify({"error": MSG.EVENT_ALREADY_CHECKED_IN}), 400
            # Catch unique-constraint violation (23505) so concurrent requests
            # that both pass the read check above don't produce a 500 — treat
            # as "already checked in" instead.
            try:
                db.table("event_checkins").insert({
                    "ticket_id": ticket_id_str,
                    "checked_in_by": g.user_id,
                    "qr_code": qr_token,
                })
            except SupabaseError as insert_err:
                err_str = str(insert_err)
                if "23505" in err_str or "duplicate" in err_str.lower() or "unique" in err_str.lower():
                    return jsonify({"error": MSG.EVENT_ALREADY_CHECKED_IN}), 400
                raise

        # ── Award HP (both RPC and fallback paths continue here) ─────────────
        from flask import current_app
        event = db.table("events").select("hp_reward,hp_per_attendee,title").eq("id", event_id).single().execute()
        # Prefer hp_per_attendee (new field); fall back to legacy hp_reward, then config
        hp_amount = (
            (event.get("hp_per_attendee") or event.get("hp_reward"))
            if event else current_app.config["EVENT_CHECKIN_HP"]
        ) or current_app.config["EVENT_CHECKIN_HP"]

        hp_result = earn_pending_hp(
            user_id=g.user_id,
            amount=hp_amount,
            source_type="event",
            reference_id=event_id,
            notes=f"Event check-in HP: {event.get('title', '') if event else ''}",
        )

        from app.services.notification_service import send_notification
        send_notification(
            user_id=g.user_id,
            notif_type="hp_earned_event",
            template_data={
                "hp": hp_result["added_to_pending"],
                "event_title": event.get("title", "the event") if event else "the event",
            },
        )

        return jsonify({
            "message": MSG.EVENT_CHECKIN_SUCCESS,
            "hp_added_to_pending": hp_result["added_to_pending"],
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@events_bp.route("/admin", methods=["GET"])
@require_role("admin")
def admin_list_events():
    """
    List all events including unpublished (admin only).
    ---
    tags: [Events]
    parameters:
      - in: query
        name: published_only
        type: boolean
        default: false
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
        description: All events for admin
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("events").select("*")
    if request.args.get("published_only", "false").lower() == "true":
        q = q.eq("is_published", "true")
    events = q.order("starts_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"events": events, "count": len(events)}), 200


@events_bp.route("/<event_id>", methods=["PATCH"])
@require_role("admin")
def update_event(event_id):
    """
    Update an event (admin only).
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            title: {type: string}
            description: {type: string}
            location: {type: string}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
            hp_reward: {type: integer}
            hp_promo_enabled: {type: boolean}
            is_featured: {type: boolean}
            is_published: {type: boolean}
            capacity: {type: integer}
    responses:
      200:
        description: Event updated
      404:
        description: Not found
    """
    db = get_db()
    event = db.table("events").select("id,starts_at,ends_at,capacity,title").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    data = request.get_json(force=True, silent=True) or {}
    EVENT_UPDATE_COLS = {
        "title", "description", "location", "starts_at", "ends_at",
        "hp_reward", "hp_promo_enabled", "is_featured", "is_published", "capacity",
        # Phase 2 columns:
        "hp_per_attendee", "funding_source", "max_attendees",
        "hp_required", "total_value", "is_paid",
    }
    # Prefer hp_per_attendee; sync to hp_reward for backward compat
    if "hp_per_attendee" in data and "hp_reward" not in data:
        data["hp_reward"] = data["hp_per_attendee"]
    safe = {k: v for k, v in data.items() if k in EVENT_UPDATE_COLS}
    if not safe:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400

    if "capacity" in safe and safe["capacity"] is not None:
        try:
            cap = int(safe["capacity"])
            if cap <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": MSG.EVENT_CAPACITY_INVALID}), 400
        issued = db.table("event_tickets").select("id").eq("event_id", event_id).execute() or []
        if cap < len(issued):
            return jsonify({"error": MSG.EVENT_CAPACITY_BELOW_ISSUED.format(issued=len(issued))}), 400
        safe["capacity"] = cap

    if "hp_reward" in safe and safe["hp_reward"] is not None:
        try:
            hp = int(safe["hp_reward"])
            if hp < 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": MSG.EVENT_HP_REWARD_INVALID}), 400
        safe["hp_reward"] = hp

    starts_at = safe.get("starts_at", event.get("starts_at"))
    ends_at = safe.get("ends_at", event.get("ends_at"))
    if ("starts_at" in safe or "ends_at" in safe) and starts_at and ends_at:
        ok, err = validate_datetime_order(starts_at, ends_at)
        if not ok:
            return jsonify({"error": err}), 400

    for bool_field in ("hp_promo_enabled", "is_featured", "is_published"):
        if bool_field in safe and not isinstance(safe[bool_field], bool):
            return jsonify({"error": f"{bool_field} must be a boolean"}), 400

    result = db.table("events").eq("id", event_id).update(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@events_bp.route("/<event_id>", methods=["DELETE"])
@require_role("admin")
def delete_event(event_id):
    """
    Delete an event (admin only). Cascades to event_tickets and checkins.
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
    responses:
      200:
        description: Event deleted
      404:
        description: Not found
    """
    db = get_db()
    event = db.table("events").select("id,title").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    # Cascade: remove check-ins and tickets before deleting event
    try:
        tickets = db.table("event_tickets").select("id").eq("event_id", event_id).execute() or []
        ticket_ids = [t["id"] for t in tickets]
        if ticket_ids:
            for tid in ticket_ids:
                db.table("event_checkins").eq("ticket_id", tid).delete()
        db.table("event_tickets").eq("event_id", event_id).delete()
    except Exception:
        pass
    db.table("events").eq("id", event_id).delete()
    return jsonify({"message": MSG.EVENT_DELETED.format(title=event.get("title", event_id))}), 200


@events_bp.route("/<event_id>/qr", methods=["POST"])
@require_role("admin")
def generate_event_qr(event_id):
    """
    Generate a QR token for event check-in (admin only).

    Returns a signed token that attendees scan at the door. The token is stored
    on the event and verified by POST /<event_id>/checkin. Regenerating
    overwrites the previous token, invalidating old QR codes.
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
    responses:
      200:
        description: QR token generated
      404:
        description: Event not found
    """
    db = get_db()
    event = db.table("events").select("id,title,metadata").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    import uuid as _uuid
    qr_token = _uuid.uuid4().hex
    metadata = dict(event.get("metadata") or {})
    metadata["qr_token"] = qr_token
    db.table("events").eq("id", event_id).update({"metadata": metadata})
    qr_payload = f"hg-event:{event_id}:{qr_token}"
    return jsonify({
        "event_id": event_id,
        "qr_token": qr_token,
        "qr_payload": qr_payload,
        "instructions": "Encode qr_payload as a QR code. Attendees scan it at checkin.",
    }), 200


@events_bp.route("/<event_id>/register", methods=["POST"])
@require_auth
def register_for_event(event_id):
    """
    Register for a Holy Grills event and receive a ticket.

    Returns a ticket_id that doubles as the qr_token for POST /<event_id>/checkin.
    The check-in RPC validates the token by matching it to the user's ticket ID,
    so attendees must call this endpoint first, then present the ticket_id at the door.

    Calling this endpoint when already registered returns the existing ticket (idempotent).
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
    responses:
      201:
        description: Ticket issued — use ticket_id as qr_token at check-in
        schema:
          properties:
            ticket_id: {type: string}
            qr_token:  {type: string, description: "Same as ticket_id — pass this to POST /checkin"}
            event_id:  {type: string}
            event_title: {type: string}
            status:    {type: string, example: confirmed}
      200:
        description: Already registered — existing ticket returned
      404:
        description: Event not found or not published
      400:
        description: Event is at capacity
    """
    db = get_db()
    data = request.get_json(force=True, silent=True) or {}
    # Try full select (including Phase-2 paid-event columns); fall back to
    # base columns if those columns haven't been migrated yet.
    try:
        event = (
            db.table("events")
            .select("id,title,capacity,is_published,starts_at,ends_at,is_paid,hp_required,total_value,cash_price")
            .eq("id", event_id)
            .single()
            .execute()
        )
    except Exception:
        event = (
            db.table("events")
            .select("id,title,capacity,is_published,starts_at,ends_at")
            .eq("id", event_id)
            .single()
            .execute()
        )
    if not event or not event.get("is_published"):
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    # Idempotent — return existing ticket if already registered
    existing = (
        db.table("event_tickets")
        .select("id,status")
        .eq("event_id", event_id)
        .eq("user_id", g.user_id)
        .single()
        .execute()
    )
    if existing:
        return jsonify({
            "ticket_id": existing["id"],
            "qr_token": existing["id"],
            "event_id": event_id,
            "event_title": event.get("title"),
            "status": existing.get("status", "confirmed"),
            "message": "Already registered — use ticket_id as qr_token to check in.",
        }), 200

    # ── Paid event: handle payment before issuing ticket ─────────────────────
    # is_paid=True → user must pay hp_required HP (if balance sufficient) + cash_price ₦,
    # OR total_value ₦ in full cash when HP is insufficient.
    ticket_payment_info = {}
    is_paid = event.get("is_paid", False)
    if is_paid:
        hp_required = int(event.get("hp_required") or 0)
        total_value = float(event.get("total_value") or 0)
        cash_price  = float(event.get("cash_price") or 0)
        payment_method = (data.get("payment_method") or "wallet").lower()
        if payment_method not in ("wallet", "card"):
            return jsonify({"error": MSG.PAID_EVENT_PAYMENT_REQUIRED}), 400

        from app.services.hp_service import get_hp_balance, spend_hp as _spend_hp
        from app.services.wallet_service import debit_wallet as _debit
        balance = get_hp_balance(g.user_id)
        user_hp = balance.get("active", 0)

        if hp_required > 0 and user_hp >= hp_required:
            hp_to_spend  = hp_required
            naira_to_pay = cash_price
            _payment_msg = resolve_msg(MSG.PAID_EVENT_HP_USED, hp=hp_to_spend, cash=naira_to_pay)
        else:
            hp_to_spend  = 0
            naira_to_pay = total_value
            _payment_msg = resolve_msg(MSG.PAID_EVENT_CASH_ONLY, total=naira_to_pay)

        if naira_to_pay > 0 and payment_method == "wallet":
            _debit(g.user_id, naira_to_pay, event_id, "event_ticket",
                   f"Event ticket: {event.get('title', '')}")

        if hp_to_spend > 0:
            _spend_hp(g.user_id, hp_to_spend, event_id, "event_ticket",
                      f"HP for event: {event.get('title', '')}")

        ticket_payment_info = {
            "hp_spent": hp_to_spend,
            "naira_charged": naira_to_pay,
            "payment_method": payment_method,
        }

    capacity = event.get("capacity")
    already_registered = False

    # Prefer the atomic RPC (locks the event row so concurrent registrations
    # serialize instead of racing on a stale capacity count). Falls back to a
    # best-effort app-level check if the RPC hasn't been deployed yet — see
    # migrations/schema.sql section 6a.
    def _fetch_existing_ticket():
        """Return existing ticket dict for (event_id, user_id) or None."""
        try:
            return (
                db.table("event_tickets")
                .select("id,status")
                .eq("event_id", event_id)
                .eq("user_id", g.user_id)
                .single()
                .execute()
            )
        except Exception:
            return None

    def _existing_ticket_response(ticket_row, status_code=200):
        return jsonify({
            "ticket_id": ticket_row["id"],
            "qr_token": ticket_row["id"],
            "event_id": event_id,
            "event_title": event.get("title"),
            "status": ticket_row.get("status", "confirmed"),
            "message": "Already registered — use ticket_id as qr_token to check in.",
        }), status_code

    try:
        rpc_result = db.rpc("register_for_event_atomic", {
            "p_event_id": event_id,
            "p_user_id": g.user_id,
        })
        # Supabase RPC may return a list of rows rather than a bare dict
        if isinstance(rpc_result, list):
            rpc_result = rpc_result[0] if rpc_result else {}
        if isinstance(rpc_result, dict) and rpc_result.get("error"):
            err_msg = rpc_result["error"]
            # "Already registered" variants from the RPC are not an error — treat as idempotent
            if "already" in err_msg.lower() or "duplicate" in err_msg.lower() or "registered" in err_msg.lower():
                # RPC may or may not echo back ticket_id on the already-registered path
                t_id = rpc_result.get("ticket_id")
                if t_id:
                    already_registered = True
                    ticket_id = t_id
                else:
                    existing = _fetch_existing_ticket()
                    if existing:
                        return _existing_ticket_response(existing)
                    # Genuinely missing ticket after RPC said already-registered — fall through
                    return jsonify({"error": err_msg}), 400
            elif err_msg == "Event not found":
                return jsonify({"error": err_msg}), 404
            else:
                return jsonify({"error": err_msg}), 400
        else:
            ticket_id = rpc_result.get("ticket_id") if isinstance(rpc_result, dict) else None
            already_registered = bool((rpc_result or {}).get("already_registered"))
    except SupabaseError as e:
        e_str = str(e)
        if "PGRST202" not in e_str and "Could not find the function" not in e_str:
            # Re-registration unique-constraint may also surface here
            if "duplicate" in e_str.lower() or "unique" in e_str.lower() or "23505" in e_str:
                existing = _fetch_existing_ticket()
                if existing:
                    return _existing_ticket_response(existing)
            raise
        # ── RPC not deployed yet — best-effort insert + post-hoc rank check ───
        try:
            ticket = db.table("event_tickets").insert({
                "event_id": event_id,
                "user_id": g.user_id,
                "status": "confirmed",
            })
            ticket_row = ticket[0] if isinstance(ticket, list) else ticket
            ticket_id = ticket_row["id"]
        except Exception:
            # Any insert failure (unique constraint, HTTP 400, etc.) → already registered
            existing = _fetch_existing_ticket()
            if existing:
                return _existing_ticket_response(existing)
            return jsonify({"error": MSG.EVENT_AT_CAPACITY}), 400

        if capacity:
            issued = (
                db.table("event_tickets")
                .select("id,created_at")
                .eq("event_id", event_id)
                .order("created_at", ascending=True)
                .execute()
            ) or []
            ordered_ids = [row["id"] for row in issued]
            rank = ordered_ids.index(ticket_id) + 1 if ticket_id in ordered_ids else len(ordered_ids)
            if rank > capacity:
                db.table("event_tickets").eq("id", ticket_id).delete()
                return jsonify({"error": MSG.EVENT_AT_CAPACITY}), 400

    if already_registered:
        return jsonify({
            "ticket_id": ticket_id,
            "qr_token": ticket_id,
            "event_id": event_id,
            "event_title": event.get("title"),
            "status": "confirmed",
            "message": "Already registered — use ticket_id as qr_token to check in.",
        }), 200

    from app.services.notification_service import send_notification
    send_notification(
        user_id=g.user_id,
        notif_type="event_registered",
        template_data={"title": event.get("title", "the event")},
        reference_id=event_id,
        reference_type="event",
    )

    response = {
        "ticket_id": ticket_id,
        "qr_token": ticket_id,
        "event_id": event_id,
        "event_title": event.get("title"),
        "status": "confirmed",
        "message": "Registration successful. Use ticket_id as qr_token to check in at the event.",
    }
    if ticket_payment_info:
        response["payment"] = ticket_payment_info
    return jsonify(response), 201


@events_bp.route("/catering-requests", methods=["GET"])
@require_role("admin")
def list_catering_requests():
    """
    List catering/event partnership requests (admin only).
    ---
    tags: [Events]
    parameters:
      - in: query
        name: status
        type: string
        enum: [new, reviewed, accepted, rejected]
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
        description: Catering request list
    """
    db = get_db()
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))
    q = db.table("catering_requests").select("*")
    status = request.args.get("status")
    if status:
        q = q.eq("status", status)
    rows = q.order("created_at", ascending=False).limit(limit).offset(offset).execute() or []
    return jsonify({"requests": rows, "count": len(rows)}), 200


@events_bp.route("/catering-requests/<request_id>", methods=["PATCH"])
@require_role("admin")
def update_catering_request(request_id):
    """
    Respond to a catering request — accept, reject, or add notes (admin only).
    ---
    tags: [Events]
    parameters:
      - in: path
        name: request_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            status: {type: string, enum: [quoted, completed, cancelled]}
            notes: {type: string}
            quoted_amount: {type: number}
            assigned_to: {type: string}
    responses:
      200:
        description: Request updated
      404:
        description: Not found
    """
    db = get_db()
    row = db.table("catering_requests").select("id,organizer_name,email").eq("id", request_id).single().execute()
    if not row:
        return jsonify({"error": MSG.EVENT_CATERING_NOT_FOUND}), 404
    data = request.get_json(force=True, silent=True) or {}
    ALLOWED = {"status", "notes", "quoted_amount", "assigned_to"}
    safe = {k: v for k, v in data.items() if k in ALLOWED}
    if not safe:
        return jsonify({"error": MSG.NO_VALID_FIELDS}), 400

    if "status" in safe:
        ok, err = validate_choice(safe["status"], CATERING_STATUSES, "status")
        if not ok:
            return jsonify({"error": err}), 400

    if "quoted_amount" in safe and safe["quoted_amount"] is not None:
        ok, err = validate_non_negative_number(safe["quoted_amount"], "quoted_amount")
        if not ok:
            return jsonify({"error": err}), 400

    if "notes" in safe and safe["notes"] is not None:
        if not isinstance(safe["notes"], str) or len(safe["notes"]) > 2000:
            return jsonify({"error": MSG.EVENT_NOTES_INVALID}), 400
        safe["notes"] = sanitize_string(safe["notes"], max_len=2000)

    if "assigned_to" in safe and safe["assigned_to"] is not None:
        if not validate_uuid(safe["assigned_to"]):
            return jsonify({"error": MSG.EVENT_ASSIGNED_TO_INVALID}), 400
        assignee = db.table("profiles").select("id,role").eq("id", safe["assigned_to"]).single().execute()
        if not assignee or assignee.get("role") not in ("admin", "staff"):
            return jsonify({"error": MSG.EVENT_ASSIGNED_TO_NOT_STAFF}), 400

    result = db.table("catering_requests").eq("id", request_id).update(safe)
    return jsonify(result[0] if isinstance(result, list) else result), 200


@events_bp.route("/catering-requests", methods=["POST"])
def submit_catering_request():
    """
    Submit a catering / event partnership request.
    ---
    tags: [Events]
    security: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [organizer_name, email, event_name, event_date, expected_guests]
          properties:
            organizer_name: {type: string}
            email: {type: string}
            phone: {type: string}
            event_name: {type: string}
            event_date: {type: string, format: date}
            expected_guests: {type: integer}
            budget: {type: number}
            notes: {type: string}
            hp_promo_optin: {type: boolean}
    responses:
      201:
        description: Request submitted
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["organizer_name", "email", "phone", "event_name", "event_date", "expected_guests"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=f)}), 400
    data["status"] = "new"
    result = db.table("catering_requests").insert(data)
    saved = result[0] if isinstance(result, list) else result

    admins = db.table("profiles").select("id").eq("role", "admin").execute()
    from app.services.notification_service import send_notification
    for admin in (admins or []):
        send_notification(
            user_id=admin["id"],
            notif_type="catering_request",
            template_data={
                "organizer": data["organizer_name"],
                "event_name": data["event_name"],
            },
            reference_id=saved["id"],
            reference_type="catering_request",
        )

    return jsonify(saved), 201


@events_bp.route("", methods=["POST"])
@require_role("admin")
def create_event():
    """
    Create a new event listing (admin only).
    ---
    tags: [Events]
    parameters:
      - in: body
        name: body
        required: true
        schema:
          required: [title, location, starts_at, hp_reward]
          properties:
            title: {type: string}
            description: {type: string}
            location: {type: string}
            starts_at: {type: string, format: date-time}
            ends_at: {type: string, format: date-time}
            hp_reward: {type: integer}
            hp_promo_enabled: {type: boolean}
            is_featured: {type: boolean}
            capacity: {type: integer}
    responses:
      201:
        description: Event created
    """
    db = get_db()
    data = request.get_json(force=True)
    required = ["title", "location", "starts_at", "hp_reward"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": MSG.AUTH_FIELD_REQUIRED.format(field=f)}), 400

    import re, uuid as _uuid
    base_slug = re.sub(r"[^a-z0-9]+", "-", data["title"].lower()).strip("-")[:54]
    data["slug"] = f"{base_slug}-{_uuid.uuid4().hex[:5]}"
    data["is_published"] = True
    data["organizer_id"] = g.user_id
    if not data.get("ends_at"):
        from datetime import datetime, timezone, timedelta
        starts = datetime.fromisoformat(data["starts_at"].replace("Z", "+00:00"))
        data["ends_at"] = (starts + timedelta(hours=3)).isoformat()
    EVENT_COLUMNS = {
        "title", "slug", "description", "location", "starts_at", "ends_at",
        "hp_reward", "hp_promo_enabled", "is_featured", "capacity",
        "is_published", "organizer_id",
        # Phase 2 columns (from migration):
        "hp_per_attendee", "funding_source", "max_attendees",
        "hp_required", "total_value", "is_paid",
    }
    # Prefer hp_per_attendee over legacy hp_reward if provided
    if data.get("hp_per_attendee") and not data.get("hp_reward"):
        data["hp_reward"] = data["hp_per_attendee"]
    safe = {k: v for k, v in data.items() if k in EVENT_COLUMNS}
    try:
        result = db.table("events").insert(safe)
    except Exception as _exc:
        # New columns may not exist yet — strip them and retry
        PHASE2_COLS = {"hp_per_attendee", "funding_source", "max_attendees", "hp_required", "total_value", "is_paid"}
        safe2 = {k: v for k, v in safe.items() if k not in PHASE2_COLS}
        result = db.table("events").insert(safe2)
    return jsonify(result[0] if isinstance(result, list) else result), 201


# ── Ticket Tiers ─────────────────────────────────────────────────────────────

@events_bp.route("/<event_id>/tiers", methods=["GET"])
def list_event_tiers(event_id):
    """
    List ticket tiers for an event (public).
    ---
    tags: [Events]
    security: []
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
    responses:
      200:
        description: Tier list
      404:
        description: Event not found
    """
    db = get_db()
    event = db.table("events").select("id,title").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404
    tiers = (
        db.table("event_ticket_tiers")
        .select("id,name,price_naira,price_hp,capacity,sold_count,description")
        .eq("event_id", event_id)
        .order("price_naira")
        .execute()
    ) or []
    return jsonify(tiers), 200


@events_bp.route("/<event_id>/tiers", methods=["POST"])
@require_role("admin")
def create_event_tier(event_id):
    """
    Create a ticket tier for an event (admin only).
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [name]
          properties:
            name: {type: string}
            price_naira: {type: number}
            price_hp: {type: integer}
            capacity: {type: integer}
            description: {type: string}
    responses:
      201:
        description: Tier created
      404:
        description: Event not found
    """
    db = get_db()
    event = db.table("events").select("id").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    data = request.get_json(force=True, silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": MSG.TIER_NAME_REQUIRED}), 400

    price_naira = data.get("price_naira", 0)
    price_hp    = data.get("price_hp", 0)
    if price_naira < 0 or price_hp < 0:
        return jsonify({"error": MSG.TIER_PRICE_INVALID}), 400

    capacity = data.get("capacity")
    if capacity is not None and (not isinstance(capacity, int) or capacity < 1):
        return jsonify({"error": MSG.TIER_CAPACITY_INVALID_TIER}), 400

    payload = {
        "event_id": event_id,
        "name": sanitize_string(name, max_len=120),
        "price_naira": price_naira,
        "price_hp": price_hp,
        "capacity": capacity,
        "description": sanitize_string(data.get("description", ""), max_len=500),
        "sold_count": 0,
    }
    result = db.table("event_ticket_tiers").insert(payload)
    saved = result[0] if isinstance(result, list) else result
    return jsonify(saved), 201


@events_bp.route("/tiers/<tier_id>", methods=["PATCH"])
@require_role("admin")
def update_event_tier(tier_id):
    """
    Update a ticket tier (admin only).
    ---
    tags: [Events]
    parameters:
      - in: path
        name: tier_id
        type: string
        required: true
      - in: body
        name: body
        schema:
          properties:
            name: {type: string}
            price_naira: {type: number}
            price_hp: {type: integer}
            capacity: {type: integer}
            description: {type: string}
    responses:
      200:
        description: Tier updated
      404:
        description: Tier not found
    """
    db = get_db()
    tier = db.table("event_ticket_tiers").select("*").eq("id", tier_id).single().execute()
    if not tier:
        return jsonify({"error": MSG.TIER_NOT_FOUND}), 404

    data = request.get_json(force=True, silent=True) or {}
    ALLOWED = {"name", "price_naira", "price_hp", "capacity", "description"}
    safe = {k: v for k, v in data.items() if k in ALLOWED}

    if "name" in safe:
        safe["name"] = sanitize_string(safe["name"], max_len=120)
    if "description" in safe:
        safe["description"] = sanitize_string(safe["description"], max_len=500)
    if "capacity" in safe and safe["capacity"] is not None:
        sold = int(tier.get("sold_count") or 0)
        if int(safe["capacity"]) < sold:
            return jsonify({"error": MSG.EVENT_CAPACITY_BELOW_ISSUED.format(issued=sold)}), 400

    result = db.table("event_ticket_tiers").eq("id", tier_id).update(safe)
    updated = result[0] if isinstance(result, list) else result
    return jsonify(updated), 200


@events_bp.route("/tiers/<tier_id>", methods=["DELETE"])
@require_role("admin")
def delete_event_tier(tier_id):
    """
    Delete a ticket tier (admin only). Forbidden if any tickets sold.
    ---
    tags: [Events]
    parameters:
      - in: path
        name: tier_id
        type: string
        required: true
    responses:
      200:
        description: Tier deleted
      400:
        description: Cannot delete — tickets already sold
      404:
        description: Tier not found
    """
    db = get_db()
    tier = db.table("event_ticket_tiers").select("*").eq("id", tier_id).single().execute()
    if not tier:
        return jsonify({"error": MSG.TIER_NOT_FOUND}), 404

    sold = int(tier.get("sold_count") or 0)
    if sold > 0:
        return jsonify({"error": MSG.TIER_DELETE_HAS_SALES, "sold_count": sold}), 400

    db.table("event_ticket_tiers").eq("id", tier_id).delete()
    return jsonify({"message": "Tier deleted"}), 200


# ── Admin event ticket export & send-to-host ──────────────────────────────────

@events_bp.route("/<event_id>/registrants", methods=["GET"])
@require_role("admin")
def list_event_registrants(event_id):
    """
    List all registrants for an event (admin only).
    Optional ?format=csv for CSV download.
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
      - in: query
        name: format
        type: string
        enum: [json, csv]
        default: json
    responses:
      200:
        description: Registrant list
      404:
        description: Event not found
    """
    db = get_db()
    event = db.table("events").select("id,title,starts_at,location").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    tickets = (
        db.table("event_tickets")
        .select("id,user_id,tier_id,status,created_at,qr_token")
        .eq("event_id", event_id)
        .order("created_at")
        .execute()
    ) or []

    # Enrich with profile and tier info
    user_ids = list({t["user_id"] for t in tickets if t.get("user_id")})
    tier_ids = list({t["tier_id"] for t in tickets if t.get("tier_id")})

    profiles = {}
    if user_ids:
        profile_rows = db.table("profiles").select("id,full_name,phone,email").in_("id", user_ids).execute() or []
        profiles = {p["id"]: p for p in profile_rows}

    tiers = {}
    if tier_ids:
        tier_rows = db.table("event_ticket_tiers").select("id,name").in_("id", tier_ids).execute() or []
        tiers = {t["id"]: t for t in tier_rows}

    # Fetch check-in status
    ticket_ids = [t["id"] for t in tickets]
    checkins = {}
    if ticket_ids:
        ci_rows = db.table("event_checkins").select("ticket_id,checked_in_at").in_("ticket_id", ticket_ids).execute() or []
        checkins = {r["ticket_id"]: r["checked_in_at"] for r in ci_rows}

    enriched = []
    for t in tickets:
        prof = profiles.get(t.get("user_id"), {})
        tier = tiers.get(t.get("tier_id"), {})
        enriched.append({
            "ticket_id":    t["id"],
            "full_name":    prof.get("full_name"),
            "phone":        prof.get("phone"),
            "email":        prof.get("email"),
            "tier_name":    tier.get("name"),
            "status":       t.get("status"),
            "registered_at": t.get("created_at"),
            "checked_in":   bool(checkins.get(t["id"])),
            "checked_in_at": checkins.get(t["id"]),
        })

    fmt = request.args.get("format", "json").lower()
    if fmt == "csv":
        import csv, io
        si = io.StringIO()
        writer = csv.DictWriter(si, fieldnames=[
            "ticket_id", "full_name", "phone", "email", "tier_name",
            "status", "registered_at", "checked_in", "checked_in_at",
        ])
        writer.writeheader()
        writer.writerows(enriched)
        from flask import make_response
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=event_{event_id}_registrants.csv"
        output.headers["Content-Type"] = "text/csv"
        return output

    return jsonify({
        "event": event,
        "registrants": enriched,
        "total": len(enriched),
    }), 200


@events_bp.route("/<event_id>/send-registrants-to-host", methods=["POST"])
@require_role("admin")
def send_registrants_to_host(event_id):
    """
    Email the full registrant list to the event organiser / host.
    Body: { "host_email": "organizer@example.com", "host_name": "Jane" }
    ---
    tags: [Events]
    parameters:
      - in: path
        name: event_id
        type: string
        required: true
      - in: body
        name: body
        required: true
        schema:
          required: [host_email]
          properties:
            host_email: {type: string, format: email}
            host_name:  {type: string}
    responses:
      200:
        description: Email sent
      404:
        description: Event not found
    """
    db = get_db()
    event = db.table("events").select("*").eq("id", event_id).single().execute()
    if not event:
        return jsonify({"error": MSG.EVENT_NOT_FOUND}), 404

    data = request.get_json(force=True, silent=True) or {}
    host_email = (data.get("host_email") or "").strip()
    host_name  = (data.get("host_name")  or "Event Organiser").strip()
    custom_message = (data.get("custom_message") or "").strip()
    if not host_email:
        return jsonify({"error": "host_email is required"}), 400

    # Build registrant table (reuse list_event_registrants logic inline)
    tickets = (
        db.table("event_tickets")
        .select("id,user_id,tier_id,status,created_at")
        .eq("event_id", event_id)
        .order("created_at")
        .execute()
    ) or []

    user_ids = list({t["user_id"] for t in tickets if t.get("user_id")})
    tier_ids = list({t["tier_id"] for t in tickets if t.get("tier_id")})

    profiles = {}
    if user_ids:
        prows = db.table("profiles").select("id,full_name,phone,email").in_("id", user_ids).execute() or []
        profiles = {p["id"]: p for p in prows}

    tiers = {}
    if tier_ids:
        trows = db.table("event_ticket_tiers").select("id,name").in_("id", tier_ids).execute() or []
        tiers = {t["id"]: t for t in trows}

    rows_html = ""
    for t in tickets:
        prof = profiles.get(t.get("user_id"), {})
        tier = tiers.get(t.get("tier_id"), {})
        rows_html += (
            f"<tr><td>{prof.get('full_name','')}</td>"
            f"<td>{prof.get('phone','')}</td>"
            f"<td>{prof.get('email','')}</td>"
            f"<td>{tier.get('name','')}</td>"
            f"<td>{t.get('status','')}</td></tr>"
        )

    html = (
        f"<html><body style='font-family:sans-serif'>"
        f"<h2>Registrants for: {event.get('title', event_id)}</h2>"
        f"<p>Date: {event.get('starts_at','')}</p>"
        f"<p>Location: {event.get('location','')}</p>"
        f"<p>Total: {len(tickets)}</p>"
        f"<p>{custom_message}</p>" if custom_message else ""
        f"<table border='1' cellpadding='6' cellspacing='0'>"
        f"<tr><th>Name</th><th>Phone</th><th>Email</th><th>Tier</th><th>Status</th></tr>"
        f"{rows_html}"
        f"</table></body></html>"
    )

    from app.utils.email import send_email_raw
    ok = send_email_raw(
        to_email=host_email,
        to_name=host_name,
        subject=f"Registrant List — {event.get('title', event_id)}",
        html_body=html,
    )
    if not ok:
        return jsonify({"error": "Failed to send email — check RESEND_API_KEY"}), 502

    return jsonify({
        "message": "Registrant list sent",
        "host_email": host_email,
        "count": len(tickets),
    }), 200
