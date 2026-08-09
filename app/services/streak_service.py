"""
Streak Service — login/check-in streak and order streak tracking.

LOGIN / CHECK-IN STREAK (rebuilt):
  Week = Monday–Sunday (ISO week).
  Daily check-in = records attendance, 0 HP.
  Up to 2 missed days reclaimable via food order OR wallet top-up ≥₦1,000
  on the missed day itself.
  Week fails if more than 2 unremedied misses.
  Week completion pays HP from login_streak_rewards table (no hardcoding):
    Week 1 → 25 HP Pending, Week 2 → 40, Week 3 → 60, Week 4+ → 80.
  Fraud-flagged check-ins silently excluded.

ORDER STREAK (new, independent):
  ≥1 delivered food order per calendar week (Mon–Sun).
  Resets to 0 on missed week.
  HP rewards from order_streak_rewards table (admin-configurable).
  HP destination: Active.

MONTHLY PENDING CAP:
  check_monthly_cap / update_monthly_tracker — used by any route awarding
  free-activity pending HP (challenges, reviews, social, etc.).
  Cap reads from system_settings key 'monthly_pending_cap' (default 1000).
"""

import math
from datetime import datetime, timezone, date, timedelta
from app.db import get_db
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_setting(db, key: str, default: str) -> str:
    try:
        row = db.table("system_settings").select("value").eq("key", key).single().execute()
        return row.get("value", default) if row else default
    except Exception:
        return default


def _monday_of_week(d: date) -> date:
    """Return the Monday of the ISO week containing d."""
    return d - timedelta(days=d.weekday())


def _week_key(d: date) -> str:
    """ISO week string 'YYYY-WW'."""
    iso = d.isocalendar()
    return f"{iso[0]:04d}-{iso[1]:02d}"


# ── Monthly cap helpers ────────────────────────────────────────────────────────

def check_monthly_cap(user_id: str, hp_to_add: int) -> dict:
    """
    Check headroom under the monthly free-activity HP cap.
    Returns {"allowed": bool, "remaining": int, "capped_amount": int}
    where capped_amount is the HP to actually award (may be < hp_to_add).

    Does NOT update the tracker — call update_monthly_tracker() after awarding.
    Cap key: 'monthly_pending_cap' in system_settings (default 1000).
    """
    db = get_db()
    cap = int(_get_setting(db, "monthly_pending_cap", "1000"))
    month = datetime.now(timezone.utc).strftime("%Y-%m")

    try:
        row = (
            db.table("monthly_hp_tracker")
            .select("total_earned")
            .eq("user_id", user_id)
            .eq("month", month)
            .single()
            .execute()
        )
        earned_so_far = int(row.get("total_earned", 0)) if row else 0
    except Exception:
        earned_so_far = 0

    remaining = max(0, cap - earned_so_far)
    if remaining <= 0:
        return {"allowed": False, "remaining": 0, "capped_amount": 0, "cap": cap}

    capped_amount = min(hp_to_add, remaining)
    return {"allowed": True, "remaining": remaining, "capped_amount": capped_amount, "cap": cap}


def update_monthly_tracker(user_id: str, hp_awarded: int) -> None:
    """Record awarded HP against the monthly cap tracker."""
    if hp_awarded <= 0:
        return
    db = get_db()
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    now = datetime.now(timezone.utc).isoformat()
    try:
        existing = (
            db.table("monthly_hp_tracker")
            .select("id,total_earned")
            .eq("user_id", user_id)
            .eq("month", month)
            .single()
            .execute()
        )
        if existing:
            db.table("monthly_hp_tracker").eq("id", existing["id"]).update({
                "total_earned": int(existing.get("total_earned", 0)) + hp_awarded,
                "updated_at": now,
            })
        else:
            db.table("monthly_hp_tracker").insert({
                "user_id": user_id,
                "month": month,
                "total_earned": hp_awarded,
                "updated_at": now,
            })
    except Exception as e:
        logger.warning("update_monthly_tracker: failed for %s: %s", user_id, e)


# ── LOGIN / CHECK-IN STREAK ────────────────────────────────────────────────────

def process_login_streak(user_id: str) -> dict:
    """
    Call on every successful authenticated login.
    Marks today as checked-in in the week_state JSONB.
    Evaluates completed/failed weeks when the week turns over.
    Fraud-flagged users: silently excluded.

    Returns:
      {"action": "started"|"same_day"|"checked_in"|"new_week_started",
       "hp_awarded": int,
       "streak_week": int,   # current cycle week number (1,2,3,4+)
       "week_start": str,
       "week_progress": {...}}
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    today = now.date()

    # Check fraud flag — silently skip
    try:
        profile = (
            db.table("profiles")
            .select("is_fraud_flagged,is_active")
            .eq("id", user_id)
            .single()
            .execute()
        )
        if (profile or {}).get("is_fraud_flagged"):
            return {"action": "excluded", "hp_awarded": 0, "streak_week": 0}
    except Exception:
        pass

    # Load or create streak record
    try:
        streak = (
            db.table("login_streaks")
            .select("*")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
    except Exception:
        streak = None

    if not streak:
        # Bootstrap
        week_start = _monday_of_week(today)
        day_offset = str((today - week_start).days)
        record = {
            "user_id": user_id,
            "streak_count": 1,
            "last_login_date": today.isoformat(),
            "last_updated": now.isoformat(),
            "current_week_start": week_start.isoformat(),
            "week_state": {day_offset: "checked"},
            "cycle_week_number": 1,
            "consecutive_weeks": 0,
        }
        try:
            db.table("login_streaks").insert(record)
        except Exception:
            # Columns may not exist yet — fall back to minimal insert
            db.table("login_streaks").insert({
                "user_id": user_id,
                "streak_count": 1,
                "last_login_date": today.isoformat(),
                "last_updated": now.isoformat(),
            })
        _touch_last_activity(db, user_id, now)
        return {
            "action": "started",
            "hp_awarded": 0,
            "streak_week": 1,
            "week_start": week_start.isoformat(),
            "week_progress": _build_week_progress({day_offset: "checked"}, week_start, today),
        }

    # Parse stored week state
    stored_week_start_str = streak.get("current_week_start")
    try:
        stored_week_start = date.fromisoformat(str(stored_week_start_str)[:10]) if stored_week_start_str else None
    except Exception:
        stored_week_start = None

    current_week_start = _monday_of_week(today)
    week_state = streak.get("week_state") or {}
    cycle_week = int(streak.get("cycle_week_number") or 1)
    consecutive_weeks = int(streak.get("consecutive_weeks") or 0)
    hp_awarded = 0
    action = "checked_in"

    # Same week — just mark today if not already marked
    if stored_week_start and stored_week_start == current_week_start:
        day_offset = str((today - current_week_start).days)
        if day_offset in week_state:
            # Already checked in today
            _touch_last_activity(db, user_id, now)
            return {
                "action": "same_day",
                "hp_awarded": 0,
                "streak_week": cycle_week,
                "week_start": current_week_start.isoformat(),
                "week_progress": _build_week_progress(week_state, current_week_start, today),
            }
        week_state[day_offset] = "checked"
        db.table("login_streaks").eq("id", streak["id"]).update({
            "week_state": week_state,
            "last_login_date": today.isoformat(),
            "last_updated": now.isoformat(),
            "streak_count": int(streak.get("streak_count") or 1) + 1,
        })
        _touch_last_activity(db, user_id, now)
        return {
            "action": "checked_in",
            "hp_awarded": 0,
            "streak_week": cycle_week,
            "week_start": current_week_start.isoformat(),
            "week_progress": _build_week_progress(week_state, current_week_start, today),
        }

    # New week — evaluate the previous week, then start fresh
    prev_week_start = stored_week_start or (current_week_start - timedelta(weeks=1))
    week_completed, cycle_week, consecutive_weeks, hp_awarded = _evaluate_week(
        db=db,
        user_id=user_id,
        prev_week_start=prev_week_start,
        week_state=week_state,
        cycle_week=cycle_week,
        consecutive_weeks=consecutive_weeks,
    )

    # Notify user when cycle fails (3+ missed days → reset to Week 1)
    if not week_completed:
        try:
            from app.services.notification_service import send_notification
            from app.messages import MSG
            send_notification(
                user_id=user_id,
                notif_type="streak_cycle_failed",
                template_data={},
            )
        except Exception:
            pass  # non-critical — never block streak processing

    # Start new week
    new_week_state = {str((today - current_week_start).days): "checked"}
    db.table("login_streaks").eq("id", streak["id"]).update({
        "current_week_start": current_week_start.isoformat(),
        "week_state": new_week_state,
        "cycle_week_number": cycle_week,
        "consecutive_weeks": consecutive_weeks,
        "last_login_date": today.isoformat(),
        "last_updated": now.isoformat(),
        "streak_count": 1 if not week_completed else int(streak.get("streak_count") or 1) + 1,
    })
    _touch_last_activity(db, user_id, now)
    return {
        "action": "new_week_started",
        "previous_week_completed": week_completed,
        "hp_awarded": hp_awarded,
        "streak_week": cycle_week,
        "week_start": current_week_start.isoformat(),
        "week_progress": _build_week_progress(new_week_state, current_week_start, today),
    }


def _evaluate_week(
    db, user_id: str,
    prev_week_start: date, week_state: dict,
    cycle_week: int, consecutive_weeks: int,
) -> tuple:
    """
    Evaluate the completed week (Sun passed). Returns:
      (week_completed: bool, new_cycle_week: int, new_consecutive: int, hp_awarded: int)
    """
    # Count effective days (checked + reclaimed) out of 7
    effective_days = len(week_state)  # every entry is 'checked' or 'reclaimed'
    missed_unremedied = 7 - effective_days  # days that passed with NO action

    hp_awarded = 0
    if missed_unremedied <= 2:
        # Week completed
        consecutive_weeks += 1
        hp_awarded = _award_login_streak_hp(db, user_id, cycle_week, consecutive_weeks)
        # Advance to next week in cycle (capped at 4)
        new_cycle_week = min(cycle_week + 1, 4) if cycle_week < 4 else 4
        return True, new_cycle_week, consecutive_weeks, hp_awarded
    else:
        # Cycle failed — reset to week 1
        return False, 1, 0, 0


def _award_login_streak_hp(db, user_id: str, cycle_week: int, consecutive_weeks: int) -> int:
    """
    Award HP for completing a check-in week. Reads from login_streak_rewards table.
    Week 4+ uses the week_number=4 row.
    HP destination: Pending. Subject to monthly cap.
    """
    week_num = min(cycle_week, 4)
    try:
        row = (
            db.table("login_streak_rewards")
            .select("hp_awarded")
            .eq("week_number", week_num)
            .eq("is_active", "true")
            .single()
            .execute()
        )
        hp = int(row.get("hp_awarded", 0)) if row else 0
    except Exception:
        # Fallback defaults
        try:
            from flask import current_app
            defaults = {
                1: current_app.config.get("LOGIN_STREAK_WEEK1_HP", 25),
                2: current_app.config.get("LOGIN_STREAK_WEEK2_HP", 40),
                3: current_app.config.get("LOGIN_STREAK_WEEK3_HP", 60),
                4: current_app.config.get("LOGIN_STREAK_WEEK4_HP", 80),
            }
        except Exception:
            defaults = {1: 25, 2: 40, 3: 60, 4: 80}
        hp = defaults.get(week_num, 25)

    if hp <= 0:
        return 0

    cap_check = check_monthly_cap(user_id, hp)
    if not cap_check["allowed"]:
        return 0

    actual_hp = cap_check["capped_amount"]
    if actual_hp <= 0:
        return 0

    from app.services.hp_service import earn_pending_hp
    try:
        earn_pending_hp(
            user_id=user_id,
            amount=actual_hp,
            source_type="streak",
            notes=f"Check-in streak week {cycle_week} completed — {actual_hp} HP pending",
        )
        update_monthly_tracker(user_id, actual_hp)
        from app.services.notification_service import send_notification
        from app.messages import MSG
        send_notification(
            user_id=user_id,
            notif_type="checkin_streak_week",
            template_data={"week": cycle_week, "hp": actual_hp},
        )
    except Exception as e:
        logger.warning("_award_login_streak_hp: failed for %s: %s", user_id, e)
        return 0

    return actual_hp


def try_reclaim_checkin(user_id: str, reclaim_type: str = "order") -> dict:
    """
    Called when a food order is delivered OR a qualifying wallet top-up happens.
    If today is a missed day in the current streak week, marks it as 'reclaimed'.
    reclaim_type: 'order' | 'wallet_topup'

    Returns {"reclaimed": bool, "day_offset": int | None}
    """
    db = get_db()
    today = date.today()
    now = datetime.now(timezone.utc)

    try:
        streak = (
            db.table("login_streaks")
            .select("id,current_week_start,week_state,cycle_week_number,consecutive_weeks")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
    except Exception:
        return {"reclaimed": False, "day_offset": None}

    if not streak:
        return {"reclaimed": False, "day_offset": None}

    week_start_str = streak.get("current_week_start")
    if not week_start_str:
        return {"reclaimed": False, "day_offset": None}

    try:
        week_start = date.fromisoformat(str(week_start_str)[:10])
    except Exception:
        return {"reclaimed": False, "day_offset": None}

    current_week_start = _monday_of_week(today)
    if week_start != current_week_start:
        # Not in the current week — nothing to reclaim
        return {"reclaimed": False, "day_offset": None}

    day_offset = str((today - week_start).days)
    week_state = streak.get("week_state") or {}

    if day_offset in week_state:
        # Today is already checked in or reclaimed
        return {"reclaimed": False, "day_offset": None}

    # Today is a missed day — mark as reclaimed
    week_state[day_offset] = "reclaimed"
    try:
        db.table("login_streaks").eq("id", streak["id"]).update({
            "week_state": week_state,
            "last_updated": now.isoformat(),
        })
        from app.services.notification_service import send_notification
        from app.messages import MSG
        send_notification(
            user_id=user_id,
            notif_type="checkin_reclaimed",
            template_data={},
        )
        return {"reclaimed": True, "day_offset": int(day_offset)}
    except Exception as e:
        logger.warning("try_reclaim_checkin: failed for %s: %s", user_id, e)
        return {"reclaimed": False, "day_offset": None}


def _build_week_progress(week_state: dict, week_start: date, today: date) -> dict:
    """Build a human-readable progress dict for the current week."""
    days = {}
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for i in range(7):
        d = week_start + timedelta(days=i)
        key = str(i)
        if key in week_state:
            status = week_state[key]  # 'checked' or 'reclaimed'
        elif d < today:
            status = "missed"
        elif d == today:
            status = "today"
        else:
            status = "upcoming"
        days[day_names[i]] = status
    return {"week_start": week_start.isoformat(), "days": days}


def get_streak(user_id: str) -> dict:
    """Return the user's current login streak info."""
    db = get_db()
    today = date.today()
    try:
        row = (
            db.table("login_streaks")
            .select("streak_count,last_login_date,current_week_start,week_state,cycle_week_number,consecutive_weeks,last_updated")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if not row:
            return {"streak_count": 0, "last_login_date": None, "cycle_week_number": 1}

        # Build week progress if we have week data
        week_progress = None
        week_start_str = row.get("current_week_start")
        if week_start_str:
            try:
                week_start = date.fromisoformat(str(week_start_str)[:10])
                week_state = row.get("week_state") or {}
                week_progress = _build_week_progress(week_state, week_start, today)
            except Exception:
                pass

        return {
            "streak_count": row.get("streak_count") or 0,
            "last_login_date": row.get("last_login_date"),
            "cycle_week_number": row.get("cycle_week_number") or 1,
            "consecutive_weeks": row.get("consecutive_weeks") or 0,
            "week_progress": week_progress,
            "last_updated": row.get("last_updated"),
        }
    except Exception:
        return {"streak_count": 0, "last_login_date": None, "cycle_week_number": 1}


def _touch_last_activity(db, user_id: str, now: datetime) -> None:
    """Update profiles.last_activity_at for decay-onset tracking."""
    try:
        db.table("profiles").eq("id", user_id).update({"last_activity_at": now.isoformat()})
    except Exception:
        pass


# ── ORDER STREAK ───────────────────────────────────────────────────────────────

def process_order_streak(user_id: str, order_id: str) -> dict:
    """
    Called when a food order is delivered.
    If this is the first qualifying order for the current ISO week, increments
    the order streak. Awards HP from order_streak_rewards table.

    Returns {"streak_weeks": int, "hp_awarded": int, "new_week": bool}
    """
    db = get_db()
    today = date.today()
    current_week = _week_key(today)
    now = datetime.now(timezone.utc).isoformat()

    # Load or create order_streaks record
    try:
        streak = (
            db.table("order_streaks")
            .select("*")
            .eq("user_id", user_id)
            .single()
            .execute()
        )
    except Exception:
        streak = None

    if not streak:
        # First ever order streak entry
        try:
            db.table("order_streaks").insert({
                "user_id": user_id,
                "streak_weeks": 1,
                "longest_streak": 1,
                "last_order_week": current_week,
                "last_updated": now,
            })
        except Exception as e:
            logger.warning("process_order_streak: insert failed for %s: %s", user_id, e)
            return {"streak_weeks": 1, "hp_awarded": 0, "new_week": True}
        hp = _award_order_streak_hp(db, user_id, 1)
        return {"streak_weeks": 1, "hp_awarded": hp, "new_week": True}

    last_week = streak.get("last_order_week")

    # Same week — already counted
    if last_week == current_week:
        return {"streak_weeks": int(streak.get("streak_weeks") or 0), "hp_awarded": 0, "new_week": False}

    # Previous week check — was last week the previous ISO week?
    try:
        prev_week_date = today - timedelta(weeks=1)
        prev_week_key = _week_key(prev_week_date)
        is_consecutive = (last_week == prev_week_key)
    except Exception:
        is_consecutive = False

    if is_consecutive:
        new_streak = int(streak.get("streak_weeks") or 0) + 1
    else:
        # Missed at least one week — reset
        new_streak = 1

    longest = max(new_streak, int(streak.get("longest_streak") or 0))

    try:
        db.table("order_streaks").eq("user_id", user_id).update({
            "streak_weeks": new_streak,
            "longest_streak": longest,
            "last_order_week": current_week,
            "last_updated": now,
        })
    except Exception as e:
        logger.warning("process_order_streak: update failed for %s: %s", user_id, e)

    hp = _award_order_streak_hp(db, user_id, new_streak)

    return {"streak_weeks": new_streak, "hp_awarded": hp, "new_week": True}


def _award_order_streak_hp(db, user_id: str, streak_weeks: int) -> int:
    """
    Award HP for hitting an order streak milestone.
    Reads from order_streak_rewards (exact weeks match only).
    HP destination: Active.
    """
    try:
        row = (
            db.table("order_streak_rewards")
            .select("hp_awarded")
            .eq("weeks", streak_weeks)
            .eq("is_active", "true")
            .single()
            .execute()
        )
        hp = int(row.get("hp_awarded", 0)) if row else 0
    except Exception:
        hp = 0

    if hp <= 0:
        return 0

    from app.services.hp_service import award_active_hp
    try:
        award_active_hp(
            user_id=user_id,
            amount=hp,
            source_type="streak",
            notes=f"Order streak milestone — {streak_weeks} consecutive week(s) → {hp} HP active",
        )
        from app.services.notification_service import send_notification
        from app.messages import MSG
        _plural = "s" if streak_weeks != 1 else ""
        send_notification(
            user_id=user_id,
            notif_type="order_streak",
            template_data={"weeks": streak_weeks, "plural": _plural, "hp": hp},
        )
    except Exception as e:
        logger.warning("_award_order_streak_hp: failed for %s: %s", user_id, e)
        return 0

    return hp
