"""
Scheduled Celery tasks — all background jobs for the HP ecosystem.

All tasks are idempotent — safe to re-run if they fail halfway.
Uses Supabase RPC cron lock pattern to prevent duplicate runs.
"""

from app.tasks.celery_app import celery_app
from app.db import get_db
from datetime import datetime, timezone, timedelta, date
from app.utils.logger import get_logger
from app.messages import MSG

logger = get_logger(__name__)


@celery_app.task(name="app.tasks.scheduled.reset_monthly_leaderboard", bind=True, max_retries=3)
def reset_monthly_leaderboard(self):
    """
    Runs: 1st of each month at 00:01 WAT.
    1. Archive top 10 of previous month to hall_of_fame (rank #1) and spin_win_entries (ranks 2-10)
    2. Reset monthly_hp_earned to 0 for all users
    3. Create leaderboard snapshot for previous month
    """
    db = get_db()
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "reset_monthly_leaderboard"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        now = datetime.now(timezone.utc)
        last_month = (now.replace(day=1) - timedelta(days=1))
        period = last_month.strftime("%Y-%m")

        # Compute top earners for last month from hp_transactions
        month_start = last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        EARN_TYPES = ["earn_order", "earn_first_order", "earn_referral", "earn_event_checkin",
                      "earn_review", "earn_birthday", "earn_challenge", "earn_admin_grant",
                      "earn_squad_bonus", "earn_streak"]
        month_txns = (
            db.table("hp_transactions")
            .select("user_id,amount")
            .in_("type", EARN_TYPES)
            .gte("created_at", month_start.isoformat())
            .lt("created_at", month_end.isoformat())
            .execute()
        )

        # Aggregate HP earned per user
        from collections import defaultdict
        user_hp = defaultdict(int)
        for t in (month_txns or []):
            if t.get("amount", 0) > 0:
                user_hp[t["user_id"]] += t["amount"]

        sorted_users = sorted(user_hp.items(), key=lambda x: x[1], reverse=True)[:10]

        if sorted_users:
            # Fetch display names for top users
            top_ids = [uid for uid, _ in sorted_users]
            profiles_data = (
                db.table("profiles")
                .select("id,full_name")
                .in_("id", top_ids)
                .execute()
            )
            profile_map = {p["id"]: p for p in (profiles_data or [])}

            entries = []
            for i, (user_id, hp_earned) in enumerate(sorted_users):
                entries.append({
                    "rank": i + 1,
                    "user_id": user_id,
                    "full_name": profile_map.get(user_id, {}).get("full_name"),
                    "hp_earned": hp_earned,
                })

            try:
                db.table("leaderboard_snapshots").insert({
                    "ranking_type": "monthly",
                    "period_key": period,
                    "entries": entries,
                })
            except Exception as e:
                logger.error("reset_monthly_leaderboard: snapshot insert failed: %s", e)

            # Notify top-10 users of their placement
            from app.services.notification_service import send_notification
            for entry in entries[:10]:
                uid = entry.get("user_id")
                rank = entry.get("rank", "?")
                hp = entry.get("hp_earned", 0)
                if not uid:
                    continue
                try:
                    send_notification(
                        user_id=uid,
                        notif_type="leaderboard_rank",
                        template_data={"rank": rank, "hp": hp, "period": period},
                    )
                except Exception as e:
                    logger.warning("reset_monthly_leaderboard: notify failed for user %s: %s", uid, e)

            # §Spec: Track top-3 finishes; induct to hall_of_fame_inductees at count=3
            top3_ids = [uid for uid, _ in sorted_users[:3]]
            for uid in top3_ids:
                try:
                    profile = db.table("profiles").select("top4_finish_count").eq("id", uid).single().execute()
                    current_count = int((profile or {}).get("top4_finish_count") or 0)
                    new_count = current_count + 1
                    db.table("profiles").eq("id", uid).update({"top4_finish_count": new_count})
                    if new_count == 3:
                        # Induct to Hall of Fame
                        try:
                            _hof_profile = db.table("profiles").select("full_name,current_tier").eq("id", uid).single().execute() or {}
                            db.table("hall_of_fame_inductees").insert({
                                "user_id": uid,
                                "inducted_at": now.isoformat(),
                                "full_name": _hof_profile.get("full_name") or ("Platform Member"),
                                "tier_at_induction": _hof_profile.get("current_tier"),
                                "top4_finish_count": new_count,
                            })
                            # Create pending reward record for admin to fulfil
                            try:
                                db.table("hall_of_fame_rewards").insert({
                                    "user_id": uid,
                                    "inducted_at": now.isoformat(),
                                    "status": "pending",
                                })
                            except Exception:
                                pass
                        except Exception as _hof_err:
                            logger.warning("reset_monthly_leaderboard: hall_of_fame insert failed for %s: %s", uid, _hof_err)
                        try:
                            send_notification(
                                user_id=uid,
                                notif_type="hall_of_fame",
                                template_data={},
                            )
                        except Exception:
                            pass
                        # Notify all admins of new inductee
                        try:
                            _admin_ids = db.table("profiles").select("id").eq("role", "admin").execute() or []
                            _hof_name = (db.table("profiles").select("full_name").eq("id", uid).single().execute() or {}).get("full_name", "A user")
                            for _adm in _admin_ids:
                                try:
                                    send_notification(
                                        user_id=_adm["id"],
                                        notif_type="admin_hof_induction",
                                        template_data={"inducted_name": _hof_name, "user_id": uid},
                                    )
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning("reset_monthly_leaderboard: top3 tracking failed for %s: %s", uid, e)

            # §Spec: Assign leaderboard prizes — free-side credits (#1-#3) + exclusive spin (#1-#10)
            try:
                from flask import current_app as _capp
                _free_days = _capp.config.get("FREE_SIDE_CREDITS_VALIDITY_DAYS", 60)
                _spin_days  = _capp.config.get("EXCLUSIVE_SPIN_VALIDITY_DAYS", 30)
                from datetime import timezone as _tz
                _now = datetime.now(_tz.utc)
                _free_expires = (_now + timedelta(days=_free_days)).isoformat()
                _spin_expires  = (_now + timedelta(days=_spin_days)).isoformat()

                FREE_SIDE_COUNTS = {1: 5, 2: 3, 3: 1}  # rank → credit count

                for entry in entries[:10]:
                    _uid = entry.get("user_id")
                    _rank = entry.get("rank", 0)
                    if not _uid:
                        continue

                    # Award exclusive spin to all top-10
                    try:
                        db.table("exclusive_spins").insert({
                            "user_id": _uid,
                            "spin_count": 1,
                            "source": "leaderboard_prize",
                            "month": period,
                            "expires_at": _spin_expires,
                        })
                    except Exception as _es:
                        logger.warning("reset_monthly_leaderboard: exclusive_spin insert failed for %s: %s", _uid, _es)

                    # Award free-side credits to #1-#3
                    _credits = FREE_SIDE_COUNTS.get(_rank, 0)
                    if _credits > 0:
                        try:
                            db.table("free_side_credits").insert({
                                "user_id": _uid,
                                "credits_remaining": _credits,
                                "source": "leaderboard_prize",
                                "month": period,
                                "expires_at": _free_expires,
                            })
                        except Exception as _fsc:
                            logger.warning("reset_monthly_leaderboard: free_side_credits insert failed for %s: %s", _uid, _fsc)

                    # Create fulfillment tracking record
                    try:
                        db.table("leaderboard_reward_fulfillments").insert({
                            "user_id": _uid,
                            "rank": _rank,
                            "month": period,
                            "reward_type": "leaderboard_prize",
                            "status": "pending",
                        })
                    except Exception:
                        pass

                    # Notify user of their prize
                    try:
                        _prize_desc = f"{FREE_SIDE_COUNTS.get(_rank, 0)} free sides + 1 exclusive spin" if _rank <= 3 else "1 exclusive spin"
                        send_notification(
                            user_id=_uid,
                            notif_type="leaderboard_prize",
                            template_data={"rank": _rank, "prize": _prize_desc, "period": period},
                        )
                    except Exception:
                        pass
            except Exception as _prize_err:
                logger.warning("reset_monthly_leaderboard: prize assignment failed: %s", _prize_err)
        else:
            entries = []

        return {"period": period, "top_count": len(entries)}
    finally:
        db.rpc("release_cron_lock", {"p_job_name": "reset_monthly_leaderboard"})


@celery_app.task(name="app.tasks.scheduled.recalculate_120day_hp", bind=True, max_retries=3)
def recalculate_120day_hp(self):
    """
    Runs: Daily at 02:00 WAT.
    Recalculates hp_earned_120day for all active users from hp_transactions
    where created_at >= now() - 120 days and type='earn' and status='active'.
    Persists the result to profiles.hp_earned_120day and triggers tier recalculation.
    """
    db = get_db()
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "recalculate_120day_hp"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        profiles = db.table("profiles").select("id").eq("is_active", "true").execute()
        updated = 0

        EARN_TYPES = ["earn_order", "earn_first_order", "earn_referral", "earn_event_checkin",
                      "earn_review", "earn_birthday", "earn_challenge", "earn_admin_grant",
                      "earn_squad_bonus", "earn_streak"]

        from app.services.hp_service import recalculate_tier

        for profile in profiles:
            user_id = profile["id"]
            try:
                txns = (
                    db.table("hp_transactions")
                    .select("amount")
                    .eq("user_id", user_id)
                    .in_("type", EARN_TYPES)
                    .eq("status", "active")
                    .gte("created_at", cutoff)
                    .execute()
                )
                earned_120 = sum(t["amount"] for t in (txns or []) if t.get("amount", 0) > 0)

                # Persist to profiles so recalculate_tier() and get_hp_balance() can read it
                try:
                    db.table("profiles").eq("id", user_id).update({
                        "hp_earned_120day": earned_120,
                    })
                except Exception as e:
                    logger.warning("recalculate_120day_hp: profile update failed for user %s: %s", user_id, e)

                # Trigger tier recalculation based on new 120-day figure
                try:
                    recalculate_tier(user_id)
                except Exception as e:
                    logger.warning("recalculate_120day_hp: tier recalc failed for user %s: %s", user_id, e)

                updated += 1
            except Exception as e:
                logger.error("recalculate_120day_hp: failed for user %s: %s", user_id, e)

        return {"updated": updated}
    finally:
        db.rpc("release_cron_lock", {"p_job_name": "recalculate_120day_hp"})


@celery_app.task(name="app.tasks.scheduled.tier_grace_period_check", bind=True, max_retries=3)
def tier_grace_period_check(self):
    """
    Runs: Daily at 03:00 WAT.
    1. Find users whose hp_earned_120day is below their current tier threshold
    2. Start 7-day grace period if not already in one
    3. Drop tier if grace period has elapsed
    """
    db = get_db()
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "tier_grace_period_check"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        from flask import current_app
        now = datetime.now(timezone.utc)
        grace_days = current_app.config.get("TIER_GRACE_PERIOD_DAYS", 7)

        tiers = db.table("hp_tiers").select("*").order("sort_order").execute()
        base_tier = tiers[0] if tiers else None

        # Build tier lookup by id
        tier_map = {t["id"]: t for t in tiers}

        # Find all active students with a current tier set
        profiles_in_tier = (
            db.table("profiles")
            .select("id,hp_earned_120day,current_tier_id,tier_grace_ends_at,tier_grace_started_at")
            .eq("is_active", "true")
            .eq("role", "student")
            .not_.is_("current_tier_id", "null")
            .execute()
        )

        started_grace = 0
        dropped_tier = 0

        from app.services.notification_service import send_notification

        for profile in (profiles_in_tier or []):
            user_id = profile["id"]
            current_tier_id = profile.get("current_tier_id")
            tier = tier_map.get(current_tier_id, {})
            maintenance = tier.get("maintenance_points", 0)
            if maintenance == 0:
                continue

            # Use hp_earned_120day (rolling 120-day) for tier maintenance check
            hp_earned_120day = profile.get("hp_earned_120day", 0) or 0
            grace_ends = profile.get("tier_grace_ends_at")

            if hp_earned_120day >= maintenance:
                # User met maintenance — clear any grace period
                if grace_ends:
                    db.table("profiles").eq("id", user_id).update({
                        "tier_grace_started_at": None,
                        "tier_grace_ends_at": None,
                    })
                continue

            if grace_ends:
                # Already in grace period — check if elapsed
                if grace_ends < now.isoformat():
                    # Grace over — find the highest tier they qualify for
                    new_tier = base_tier
                    for t in reversed(tiers):
                        if hp_earned_120day >= t.get("min_points", 0):
                            new_tier = t
                            break

                    new_tier_id = new_tier["id"] if new_tier else None
                    db.table("profiles").eq("id", user_id).update({
                        "current_tier_id": new_tier_id,
                        "tier_grace_started_at": None,
                        "tier_grace_ends_at": None,
                    })

                    if new_tier_id:
                        db.table("user_tiers").insert({
                            "user_id": user_id,
                            "tier_id": new_tier_id,
                            "previous_tier_id": current_tier_id,
                            "event": "downgrade",
                            "hp_at_event": hp_earned_120day,
                        })

                    send_notification(
                        user_id=user_id,
                        notif_type="tier_downgrade",
                        template_data={
                            "from_tier": tier.get("name", "tier"),
                            "to_tier": new_tier.get("name", "") if new_tier else "Base",
                        },
                    )
                    dropped_tier += 1
            else:
                # Start grace period (days from config)
                grace_start = now.isoformat()
                grace_end = (now + timedelta(days=grace_days)).isoformat()
                db.table("profiles").eq("id", user_id).update({
                    "tier_grace_started_at": grace_start,
                    "tier_grace_ends_at": grace_end,
                })

                send_notification(
                    user_id=user_id,
                    notif_type="tier_grace_period",
                    template_data={
                        "grace_days": grace_days,
                        "tier_name": tier.get("name", "your tier"),
                    },
                )
                started_grace += 1

        return {"started_grace": started_grace, "dropped_tier": dropped_tier}
    finally:
        db.rpc("release_cron_lock", {"p_job_name": "tier_grace_period_check"})



@celery_app.task(name="app.tasks.scheduled.birthday_hp_awards", bind=True, max_retries=3)
def birthday_hp_awards(self):
    """
    Runs: Daily at 08:00 WAT.
    Award birthday HP (BIRTHDAY_HP env var, default 150) ACTIVE to users whose birthday is today.
    30-day redemption window communicated in notification.
    """
    from flask import current_app
    birthday_hp = current_app.config.get("BIRTHDAY_HP", 150)

    db = get_db()
    today = datetime.now(timezone.utc)
    today_md = today.strftime("%m-%d")

    profiles = (
        db.table("profiles")
        .select("id,full_name,date_of_birth")
        .eq("is_active", "true")
        .execute()
    )

    awarded = 0
    from app.services.hp_service import award_active_hp
    from app.services.notification_service import send_notification

    for profile in profiles:
        dob = profile.get("date_of_birth")
        if not dob:
            continue
        try:
            dob_md = str(dob)[5:][:5]
            if dob_md == today_md:
                already = (
                    db.table("hp_transactions")
                    .select("id")
                    .eq("user_id", profile["id"])
                    .eq("reference_type", "birthday")
                    .gte("created_at", today.replace(month=today.month, day=1, hour=0, minute=0, second=0, microsecond=0).isoformat())
                    .execute()
                )
                if already:
                    continue

                award_active_hp(
                    user_id=profile["id"],
                    amount=birthday_hp,
                    txn_type="earn_birthday",
                    reference_type="birthday",
                    notes=f"Birthday HP — {today.strftime('%B %d, %Y')}",
                    apply_multiplier=False,  # Birthday HP is fixed — not subject to event multiplier
                )

                # Blast faculty/dept notification with tap-to-HP-transfer link
                name = (profile.get("full_name") or "").split()[0]
                faculty = profile.get("faculty", "")
                dept = profile.get("department", "")
                transfer_link = f"/hp/transfer?recipient_id={profile['id']}"
                send_notification(
                    user_id=profile["id"],
                    notif_type="birthday_bonus",
                    template_data={"name": name, "hp": birthday_hp},
                    metadata={"transfer_link": transfer_link, "faculty": faculty, "department": dept},
                )

                # Blast to faculty/dept peers so they can send HP as a gift
                if faculty or dept:
                    try:
                        peer_query = (
                            db.table("profiles")
                            .select("id")
                            .eq("is_active", "true")
                            .neq("id", profile["id"])
                        )
                        if faculty:
                            peer_query = peer_query.eq("faculty", faculty)
                        if dept:
                            peer_query = peer_query.eq("department", dept)
                        peers = peer_query.execute() or []
                        for peer in peers:
                            try:
                                send_notification(
                                    user_id=peer["id"],
                                    notif_type="birthday_blast",
                                    template_data={"name": name},
                                    metadata={"transfer_link": transfer_link, "celebrant_id": profile["id"]},
                                )
                            except Exception as _pe:
                                logger.warning(
                                    "birthday_hp_awards: peer blast failed for peer %s: %s",
                                    peer["id"], _pe,
                                )
                    except Exception as _be:
                        logger.warning(
                            "birthday_hp_awards: peer blast query failed for celebrant %s: %s",
                            profile["id"], _be,
                        )

                awarded += 1
        except Exception as e:
            logger.error("birthday_hp_awards: failed for user %s: %s", profile["id"], e)

    return {"awarded": awarded, "date": today_md}


@celery_app.task(name="app.tasks.scheduled.monthly_birthday_report", bind=True, max_retries=2)
def monthly_birthday_report(self):
    """
    Runs: 1st of each month at 07:00 WAT.
    Sends each admin an in-app notification + email listing every user
    whose birthday falls in the current month (name, date MM-DD, phone).
    Admins use this to send birthday wishes, WhatsApp DMs, or social posts.
    """
    db = get_db()
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "monthly_birthday_report"})
        if not lock_acquired:
            return {"skipped": "Lock not acquired"}
    except Exception:
        lock_acquired = True

    try:
        now = datetime.now(timezone.utc)
        current_month = now.month

        profiles = (
            db.table("profiles")
            .select("id,full_name,date_of_birth,phone")
            .eq("is_active", "true")
            .execute()
        )

        birthday_users = []
        for p in (profiles or []):
            dob = p.get("date_of_birth")
            if not dob:
                continue
            try:
                dob_str = str(dob)
                month = int(dob_str[5:7])
                if month == current_month:
                    day = int(dob_str[8:10])
                    birthday_users.append({
                        "name": p.get("full_name") or "Unknown",
                        "date": dob_str[5:10],
                        "phone": p.get("phone") or "N/A",
                        "user_id": p["id"],
                    })
            except Exception:
                continue

        birthday_users.sort(key=lambda x: x["date"])
        month_name = now.strftime("%B %Y")
        count = len(birthday_users)

        admins = (
            db.table("profiles")
            .select("id,email,full_name")
            .eq("role", "admin")
            .eq("is_active", "true")
            .execute()
        )

        if not admins:
            return {"birthday_count": count, "month": month_name, "notified_admins": 0}

        summary_lines = [
            f"• {u['name']} — {u['date']} (📞 {u['phone']})"
            for u in birthday_users
        ]
        summary_text = "\n".join(summary_lines) if summary_lines else "No birthdays this month."

        notif_body = (
            f"Users with birthdays in {month_name}:\n\n{summary_text}"
            if birthday_users
            else f"No users have birthdays in {month_name}."
        )

        from app.services.notification_service import send_notification
        from app.utils.email import send_email

        for admin in admins:
            # birthday_report body is dynamically assembled from a user list — passed directly.
            send_notification(
                user_id=admin["id"],
                notif_type="birthday_report",
                title=MSG.BIRTHDAY_REPORT_TITLE.format(
                    count=count,
                    plural="s" if count != 1 else "",
                    month=month_name,
                ),
                body=notif_body,
            )
            if admin.get("email"):
                send_email(
                    to_email=admin["email"],
                    to_name=admin.get("full_name") or "Admin",
                    template_key="monthly_birthday_report",
                    data={
                        "month": month_name,
                        "count": count,
                        "birthday_list": birthday_users,
                        "summary_text": summary_text,
                    },
                )

        return {
            "birthday_count": count,
            "month": month_name,
            "notified_admins": len(admins),
        }
    finally:
        try:
            db.rpc("release_cron_lock", {"p_job_name": "monthly_birthday_report"})
        except Exception:
            pass


@celery_app.task(name="app.tasks.scheduled.process_scheduled_orders", bind=True, max_retries=3)
def process_scheduled_orders(self):
    """
    Runs: Every 5 minutes.
    Finds scheduled orders whose delivery window start time has arrived and
    notifies kitchen/admin staff so they can begin preparation.
    Orders are placed with is_scheduled=True; they stay at status='received'
    but are hidden from the kitchen board until this task fires.
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    try:
        due_orders = (
            db.table("orders")
            .select("id,scheduled_for,delivery_window_id")
            .eq("is_scheduled", "true")
            .eq("status", "received")
            .lte("scheduled_for", now.isoformat())
            .execute()
        ) or []
    except Exception as e:
        logger.error("process_scheduled_orders: query failed: %s", e)
        return {"error": str(e)}

    if not due_orders:
        return {"processed": 0, "checked_at": now.isoformat()}

    # Notify every kitchen and admin user once per due order
    try:
        staff = (
            db.table("profiles")
            .select("id")
            .in_("role", ["admin", "kitchen"])
            .eq("is_active", "true")
            .execute()
        ) or []
    except Exception:
        staff = []

    from app.services.notification_service import send_notification

    # Dedupe window: only notify once per order per 10-minute window.
    # Check the notifications table so repeated task runs (every 5 min) don't spam staff.
    dedup_cutoff = (now - timedelta(minutes=10)).isoformat()

    processed = 0
    skipped = 0
    for order in due_orders:
        order_id = order["id"]
        short_id = order_id[:8].upper()

        # Skip if we already fired this notification for this specific order recently
        try:
            already_sent = (
                db.table("notifications")
                .select("id")
                .eq("type", "scheduled_order_due")
                .gte("created_at", dedup_cutoff)
                .execute()
            )
            # Check if any recent notification body mentions this order
            already_sent_for_order = any(
                short_id in str(n.get("body", "") or "")
                for n in (already_sent or [])
            )
        except Exception:
            already_sent_for_order = False

        if already_sent_for_order:
            skipped += 1
            continue

        for member in staff:
            try:
                send_notification(
                    user_id=member["id"],
                    notif_type="scheduled_order_due",
                    template_data={"order_id": short_id},
                )
            except Exception as e:
                logger.warning("process_scheduled_orders: notify failed for staff %s: %s", member["id"], e)
        processed += 1

    return {"processed": processed, "skipped": skipped, "checked_at": now.isoformat()}


@celery_app.task(name="app.tasks.scheduled.win_back_notifications", bind=True, max_retries=3)
def win_back_notifications(self):
    """
    Runs: Daily at 10:00 WAT.
    Sends dormancy win-back notifications at day 70, 95, and 118 of inactivity.
    HP decay begins at day 120 (handled by hp_decay_check task).
    """
    db = get_db()
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "win_back_notifications"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        from flask import current_app
        from app.services.notification_service import send_notification

        now = datetime.now(timezone.utc)
        day70 = current_app.config.get("WINBACK_DAY1", 70)
        day95 = current_app.config.get("WINBACK_DAY2", 95)
        day118 = current_app.config.get("WINBACK_DAY3", 118)
        decay_onset_default = current_app.config.get("HP_DECAY_ONSET_DAYS", 120)

        # Load onset days from system_settings if available
        try:
            onset_row = db.table("system_settings").select("value").eq("key", "decay_onset_days").single().execute()
            decay_onset = int(onset_row.get("value", decay_onset_default)) if onset_row else decay_onset_default
        except Exception:
            decay_onset = decay_onset_default

        # We need users where last_activity_at is within our target bands
        results = {"day70": 0, "day95": 0, "day118": 0}

        def _is_in_band(days_inactive: int, target: int, tolerance: int = 1) -> bool:
            return target <= days_inactive <= target + tolerance

        profiles = (
            db.table("profiles")
            .select("id,hp_balance,last_activity_at")
            .eq("is_active", "true")
            .eq("role", "student")
            .not_.is_("last_activity_at", "null")
            .execute()
        ) or []

        for profile in profiles:
            user_id = profile["id"]
            hp_balance = int(profile.get("hp_balance") or 0)
            if hp_balance <= 0:
                continue

            last_activity = profile.get("last_activity_at")
            if not last_activity:
                continue

            try:
                last_dt = datetime.fromisoformat(str(last_activity).replace("Z", "+00:00"))
                days_inactive = (now - last_dt.replace(tzinfo=timezone.utc)).days
            except Exception:
                continue

            # Check dedup window (7 days) per notification type
            def _already_sent(notif_type: str) -> bool:
                try:
                    existing = (
                        db.table("notifications")
                        .select("id")
                        .eq("user_id", user_id)
                        .eq("type", notif_type)
                        .gte("created_at", (now - timedelta(days=7)).isoformat())
                        .limit(1)
                        .execute()
                    )
                    return bool(existing)
                except Exception:
                    return False

            try:
                if _is_in_band(days_inactive, day118):
                    if not _already_sent("winback_118"):
                        send_notification(
                            user_id=user_id,
                            notif_type="winback_118",
                            template_data={},
                        )
                        results["day118"] += 1
                elif _is_in_band(days_inactive, day95):
                    days_to_decay = decay_onset - days_inactive
                    if not _already_sent("winback_95"):
                        send_notification(
                            user_id=user_id,
                            notif_type="winback_95",
                            template_data={"days": max(0, days_to_decay)},
                        )
                        results["day95"] += 1
                elif _is_in_band(days_inactive, day70):
                    if not _already_sent("winback_70"):
                        send_notification(
                            user_id=user_id,
                            notif_type="winback_70",
                            template_data={},
                        )
                        results["day70"] += 1
            except Exception as e:
                logger.warning("win_back_notifications: error for user %s: %s", user_id, e)

        return results
    finally:
        try:
            db.rpc("release_cron_lock", {"p_job_name": "win_back_notifications"})
        except Exception:
            pass


@celery_app.task(name="app.tasks.scheduled.hp_decay_check", bind=True, max_retries=3)
def hp_decay_check(self):
    """
    Runs: Daily at 05:00 WAT.
    Applies 10%/month HP decay after 120 days of inactivity.
    (Flat rule — no tier variation. Replaces old 90-day expiry model.)
    """
    db = get_db()
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "hp_decay_check"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        from flask import current_app
        from app.services.hp_service import expire_hp
        from app.services.notification_service import send_notification

        now = datetime.now(timezone.utc)
        onset_days_default = current_app.config.get("HP_DECAY_ONSET_DAYS", 120)
        decay_rate_default = current_app.config.get("HP_DECAY_RATE_MONTHLY", 0.10)

        # Load from system_settings (live editable)
        try:
            onset_row = db.table("system_settings").select("value").eq("key", "decay_onset_days").single().execute()
            onset_days = int(onset_row.get("value", onset_days_default)) if onset_row else onset_days_default
        except Exception:
            onset_days = onset_days_default

        try:
            rate_row = db.table("system_settings").select("value").eq("key", "decay_rate_monthly").single().execute()
            decay_rate = float(rate_row.get("value", decay_rate_default)) if rate_row else decay_rate_default
        except Exception:
            decay_rate = decay_rate_default

        # Monthly rate → daily rate approximation (compound: apply daily = monthly^(1/30))
        daily_rate = (1 + decay_rate) ** (1 / 30) - 1

        profiles = (
            db.table("profiles")
            .select("id,hp_balance,last_activity_at")
            .eq("is_active", "true")
            .eq("role", "student")
            .not_.is_("last_activity_at", "null")
            .execute()
        ) or []

        decayed = 0
        for profile in profiles:
            user_id = profile["id"]
            hp_balance = int(profile.get("hp_balance") or 0)
            if hp_balance <= 0:
                continue

            last_activity = profile.get("last_activity_at")
            if not last_activity:
                continue

            try:
                last_dt = datetime.fromisoformat(str(last_activity).replace("Z", "+00:00"))
                days_inactive = (now - last_dt.replace(tzinfo=timezone.utc)).days
            except Exception:
                continue

            if days_inactive < onset_days:
                continue

            # Apply daily compound decay
            decay_amount = max(1, int(hp_balance * daily_rate))
            try:
                expire_hp(
                    user_id,
                    decay_amount,
                    f"HP decay — {days_inactive} days inactivity (daily rate {daily_rate:.4f})",
                )
                send_notification(
                    user_id=user_id,
                    notif_type="hp_decay_applied",
                    template_data={"amount": decay_amount, "days": days_inactive},
                )
                decayed += 1
            except Exception as e:
                logger.warning("hp_decay_check: error for user %s: %s", user_id, e)

        return {"users_decayed": decayed, "onset_days": onset_days, "daily_rate": round(daily_rate, 5)}
    finally:
        try:
            db.rpc("release_cron_lock", {"p_job_name": "hp_decay_check"})
        except Exception:
            pass


@celery_app.task(name="app.tasks.scheduled.check_order_locks", bind=True, max_retries=3)
def check_order_locks(self):
    """
    Runs: Daily at 09:00 WAT.
    1. Sends reminders for active locks at 7-10 days, 3 days, and 1 day before locked_date.
    2. Marks locks as 'expired' if locked_date has passed and status is still 'active'.
    """
    db = get_db()
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "check_order_locks"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        from app.services.notification_service import send_notification
        now = datetime.now(timezone.utc)
        today = now.date()

        active_locks = (
            db.table("order_locks")
            .select("*")
            .eq("status", "active")
            .execute()
        ) or []

        reminded = 0
        expired = 0

        for lock in active_locks:
            try:
                locked_date = date.fromisoformat(str(lock.get("locked_date", ""))[:10])
            except Exception:
                continue

            days_until = (locked_date - today).days

            if days_until < 0:
                # Lock date passed — expire it
                db.table("order_locks").eq("id", lock["id"]).update({
                    "status": "expired",
                    "updated_at": now.isoformat(),
                })
                expired += 1
                continue

            user_id = lock.get("user_id")
            if not user_id:
                continue

            # Reminder schedule: 7-10 days, 3 days, 1 day before
            should_remind = days_until in (10, 7, 3, 1)
            if not should_remind:
                continue

            last_reminder = lock.get("reminder_sent_at")
            if last_reminder:
                try:
                    last_r_dt = datetime.fromisoformat(str(last_reminder).replace("Z", "+00:00"))
                    if (now - last_r_dt.replace(tzinfo=timezone.utc)).days < 1:
                        continue
                except Exception:
                    pass

            reward_type = lock.get("reward_type", "discount")
            try:
                _plural = "s" if days_until != 1 else ""
                if reward_type == "hp":
                    hp_amount = int(lock.get("reward_hp_amount") or 0)
                    send_notification(
                        user_id=user_id,
                        notif_type="order_lock_reminder_hp",
                        template_data={
                            "days": days_until,
                            "plural": _plural,
                            "hp": hp_amount,
                            "date": locked_date.strftime("%B %d"),
                        },
                        channels=["push", "in_app"],
                    )
                else:
                    discount_pct = float(lock.get("discount_pct", 10))
                    send_notification(
                        user_id=user_id,
                        notif_type="order_lock_reminder",
                        template_data={
                            "days": days_until,
                            "plural": _plural,
                            "pct": discount_pct,
                            "date": locked_date.strftime("%B %d"),
                        },
                        channels=["push", "in_app"],
                    )
                db.table("order_locks").eq("id", lock["id"]).update({
                    "reminder_sent_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                })
                reminded += 1
            except Exception as e:
                logger.warning("check_order_locks: reminder failed for lock %s: %s", lock["id"], e)

        return {"reminders_sent": reminded, "expired": expired}
    finally:
        try:
            db.rpc("release_cron_lock", {"p_job_name": "check_order_locks"})
        except Exception:
            pass


@celery_app.task(name="app.tasks.scheduled.reset_monthly_hp_tracker", bind=True, max_retries=2)
def reset_monthly_hp_tracker(self):
    """
    Runs: 1st of each month at 00:05 WAT.
    Resets the monthly_hp_tracker for all users (new month, fresh cap).
    Old rows are deleted so the cap starts clean.
    """
    db = get_db()
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "reset_monthly_hp_tracker"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        now = datetime.now(timezone.utc)
        prev_month = (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        # Delete previous month rows to keep the table lean
        try:
            db.table("monthly_hp_tracker").eq("month", prev_month).delete()
        except Exception as e:
            logger.warning("reset_monthly_hp_tracker: delete failed: %s", e)

        return {"reset_for_month": prev_month}
    finally:
        try:
            db.rpc("release_cron_lock", {"p_job_name": "reset_monthly_hp_tracker"})
        except Exception:
            pass


@celery_app.task(name="app.tasks.scheduled.membership_anniversary_awards", bind=True, max_retries=3)
def membership_anniversary_awards(self):
    """
    Runs: Daily at 06:00 WAT.
    Awards HP to users on their membership anniversary milestones
    (3, 6, 12, 24, 36, 48, 60 months since created_at), using
    the membership_rewards table seeded by the Phase 2 migration.
    """
    db = get_db()
    try:
        lock_acquired = db.rpc("try_acquire_cron_lock", {"p_job_name": "membership_anniversary_awards"})
    except Exception:
        lock_acquired = True
    if not lock_acquired:
        return {"skipped": "Lock not acquired"}

    try:
        now = datetime.now(timezone.utc)
        today = now.date()

        # Load milestone config from DB
        rewards = (
            db.table("membership_rewards")
            .select("months,hp_awarded")
            .execute()
        ) or []
        if not rewards:
            return {"skipped": "No membership_rewards configured"}

        reward_map = {int(r["months"]): int(r["hp_awarded"]) for r in rewards}
        month_milestones = set(reward_map.keys())

        # Fetch all active students
        profiles = (
            db.table("profiles")
            .select("id,full_name,created_at")
            .eq("is_active", "true")
            .eq("role", "student")
            .execute()
        ) or []

        from app.services.hp_service import award_active_hp
        from app.services.notification_service import send_notification

        awarded = 0
        for profile in profiles:
            created_at_str = profile.get("created_at")
            if not created_at_str:
                continue
            try:
                created_dt = datetime.fromisoformat(str(created_at_str).replace("Z", "+00:00"))
                months_member = (now - created_dt).days // 30
            except Exception:
                continue

            if months_member not in month_milestones:
                continue

            # Check the signup day matches today (prevent re-triggering every day)
            signup_day = created_dt.day
            if today.day != signup_day:
                continue

            hp_amount = reward_map[months_member]

            # Dedup: check if we already awarded this milestone this month
            already = (
                db.table("hp_transactions")
                .select("id")
                .eq("user_id", profile["id"])
                .eq("reference_type", "membership_anniversary")
                .gte("created_at", f"{today.year}-{today.month:02d}-01T00:00:00+00:00")
                .execute()
            )
            if already:
                continue

            try:
                award_active_hp(
                    user_id=profile["id"],
                    amount=hp_amount,
                    txn_type="earn_membership",
                    reference_type="membership_anniversary",
                    notes=f"Membership anniversary — {months_member} months",
                    apply_multiplier=False,
                )
                from app.messages import MSG
                name = (profile.get("full_name") or "").split()[0] or MSG.ANNIVERSARY_FALLBACK_NAME
                send_notification(
                    user_id=profile["id"],
                    notif_type="membership_anniversary",
                    template_data={"months": months_member, "name": name, "hp": hp_amount},
                )
                awarded += 1
            except Exception as e:
                logger.warning("membership_anniversary_awards: failed for user %s: %s", profile["id"], e)

        return {"awarded": awarded, "date": today.isoformat()}
    finally:
        try:
            db.rpc("release_cron_lock", {"p_job_name": "membership_anniversary_awards"})
        except Exception:
            pass


@celery_app.task(name="app.tasks.scheduled.send_scheduled_notifications", bind=True, max_retries=3)
def send_scheduled_notifications(self):
    """
    Runs: Every 15 minutes.
    Delivers admin-created scheduled notification campaigns whose
    next_send_at has passed and is_active=True.

    Audience targeting via target_segment:
      'all'                  → all active users
      'tier:<slug>'          → users on that HP tier
      'faculty:<name>'       → users with matching faculty
      'department:<name>'    → users with matching department
      'user:<user_id>'       → single user

    After delivery:
      frequency='once'    → set is_active=False, update last_sent_at
      frequency='daily'   → update last_sent_at, compute next next_send_at (+1 day)
      frequency='weekly'  → update last_sent_at, compute next next_send_at (+7 days)
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    try:
        pending = (
            db.table("scheduled_notifications")
            .select("*")
            .eq("is_active", True)
            .lte("next_send_at", now.isoformat())
            .execute()
        ) or []
    except Exception as e:
        logger.error("send_scheduled_notifications: query failed: %s", e)
        return {"error": str(e)}

    if not pending:
        return {"sent": 0, "checked_at": now.isoformat()}

    from app.services.notification_service import send_notification
    from datetime import timedelta
    sent_count = 0

    for campaign in pending:
        campaign_id = campaign.get("id")
        # Column is target_segment in the schema
        segment   = campaign.get("target_segment", "all")
        title     = campaign.get("title", "")
        body      = campaign.get("body", "")
        channels  = campaign.get("channels") or ["push", "in_app"]
        notif_type = campaign.get("notif_type", "campaign")
        frequency  = campaign.get("frequency", "once")
        send_time  = campaign.get("send_time", "09:00")

        try:
            # ── Resolve recipient list ────────────────────────────────────────
            if segment == "all":
                recipients = (
                    db.table("profiles").select("id").eq("is_active", "true").execute()
                ) or []
                user_ids = [r["id"] for r in recipients]

            elif segment.startswith("tier:"):
                tier_slug = segment[5:]
                tier_row = (
                    db.table("hp_tiers").select("id").eq("slug", tier_slug).single().execute()
                )
                if not tier_row:
                    logger.warning("send_scheduled_notifications: unknown tier '%s' for campaign %s",
                                   tier_slug, campaign_id)
                    user_ids = []
                else:
                    profs = (
                        db.table("profiles")
                        .select("id")
                        .eq("current_tier_id", tier_row["id"])
                        .eq("is_active", "true")
                        .execute()
                    ) or []
                    user_ids = [p["id"] for p in profs]

            elif segment.startswith("faculty:"):
                faculty_val = segment[8:]
                profs = (
                    db.table("profiles")
                    .select("id")
                    .eq("faculty", faculty_val)
                    .eq("is_active", "true")
                    .execute()
                ) or []
                user_ids = [p["id"] for p in profs]

            elif segment.startswith("department:"):
                dept_val = segment[11:]
                profs = (
                    db.table("profiles")
                    .select("id")
                    .eq("department", dept_val)
                    .eq("is_active", "true")
                    .execute()
                ) or []
                user_ids = [p["id"] for p in profs]

            elif segment.startswith("user:"):
                user_ids = [segment[5:]]

            else:
                logger.warning("send_scheduled_notifications: unknown segment '%s' for campaign %s",
                               segment, campaign_id)
                user_ids = []

            # ── Deliver ───────────────────────────────────────────────────────
            for uid in user_ids:
                try:
                    send_notification(
                        user_id=uid,
                        notif_type=notif_type,
                        title=title,
                        body=body,
                        reference_id=campaign_id,
                        reference_type="scheduled_notification",
                        channels=channels,
                    )
                except Exception as e:
                    logger.warning("send_scheduled_notifications: notify failed for user %s "
                                   "campaign %s: %s", uid, campaign_id, e)

            # ── Update campaign state ─────────────────────────────────────────
            update_payload: dict = {"last_sent_at": now.isoformat()}
            if frequency == "once":
                update_payload["is_active"] = False
            elif frequency == "daily":
                next_dt = now + timedelta(days=1)
                update_payload["next_send_at"] = next_dt.strftime(f"%Y-%m-%dT{send_time}:00+00:00")
            elif frequency == "weekly":
                next_dt = now + timedelta(weeks=1)
                update_payload["next_send_at"] = next_dt.strftime(f"%Y-%m-%dT{send_time}:00+00:00")

            db.table("scheduled_notifications").eq("id", campaign_id).update(update_payload)
            sent_count += 1

        except Exception as e:
            logger.error("send_scheduled_notifications: campaign %s failed: %s", campaign_id, e)

    return {"sent": sent_count, "checked_at": now.isoformat()}


@celery_app.task(name="app.tasks.scheduled.scan_abandoned_carts", bind=True)
def scan_abandoned_carts(self):
    """
    Runs: Every 30 minutes.
    Flags carts inactive for 60+ minutes as abandoned.
    """
    db = get_db()
    from datetime import datetime, timezone, timedelta
    from flask import current_app
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(minutes=current_app.config.get("ABANDONED_CART_MINUTES", 60))).isoformat()

    # Find all unrecovered abandoned carts that are past the inactivity threshold
    abandoned = (
        db.table("abandoned_carts")
        .select("id,user_id")
        .eq("is_recovered", "false")
        .lt("updated_at", cutoff)
        .execute()
    ) or []

    from app.services.notification_service import send_notification
    notified = 0
    for cart in abandoned:
        user_id = cart.get("user_id")
        if not user_id:
            continue

        # Avoid spamming — only send one recovery nudge per user per 24 hours
        already_notified = (
            db.table("notifications")
            .select("id")
            .eq("user_id", user_id)
            .eq("type", "abandoned_cart")
            .gte("created_at", (now - timedelta(hours=24)).isoformat())
            .limit(1)
            .execute()
        )
        if already_notified:
            continue

        send_notification(
            user_id=user_id,
            notif_type="abandoned_cart",
            template_data={},
        )
        notified += 1

    return {"scanned": len(abandoned), "notified": notified, "cutoff": cutoff}


@celery_app.task(name="app.tasks.scheduled.check_post_delivery_nudges", bind=True, max_retries=3)
def check_post_delivery_nudges(self):
    """
    Runs: Every 30 minutes.

    RUN 8 post-delivery notification sequence:
      8.2  satisfaction_check  — sent ~2 hours after delivery  (in-app + push)
      8.3  reengagement_nudge  — sent ~24 hours after delivery  (in-app only)

    Uses order_status_logs to find when each order was delivered.
    Checks notifications table to avoid re-sending on each run.
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    results = {"satisfaction_check": 0, "reengagement_nudge": 0, "errors": 0}

    # Windows (min, max) around delivery timestamp for each nudge type
    windows = {
        "satisfaction_check": (timedelta(hours=1, minutes=30), timedelta(hours=2, minutes=30)),
        "reengagement_nudge": (timedelta(hours=23), timedelta(hours=25)),
    }

    for notif_type, (min_delta, max_delta) in windows.items():
        earliest = (now - max_delta).isoformat()
        latest   = (now - min_delta).isoformat()

        # Find orders whose delivered status log falls in this window
        delivered_logs = (
            db.table("order_status_logs")
            .select("order_id,created_at")
            .eq("status", "delivered")
            .gte("created_at", earliest)
            .lte("created_at", latest)
            .execute()
        ) or []

        for log in delivered_logs:
            order_id = log["order_id"]
            try:
                # Fetch the order to get the user_id
                order = (
                    db.table("orders")
                    .select("user_id,status")
                    .eq("id", order_id)
                    .single()
                    .execute()
                )
                if not order:
                    continue
                user_id = order.get("user_id")
                if not user_id:
                    continue

                # Skip if this nudge was already sent for this order
                already_sent = (
                    db.table("notifications")
                    .select("id")
                    .eq("user_id", user_id)
                    .eq("type", notif_type)
                    .eq("reference_id", order_id)
                    .limit(1)
                    .execute()
                )
                if already_sent:
                    continue

                send_notification(
                    user_id=user_id,
                    notif_type=notif_type,
                    template_data={},
                    reference_id=order_id,
                    reference_type="order",
                )
                results[notif_type] += 1

            except Exception as e:
                logger.warning(
                    "check_post_delivery_nudges: error for order %s / %s: %s",
                    order_id, notif_type, e,
                )
                results["errors"] += 1

    return results
