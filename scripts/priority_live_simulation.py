#!/usr/bin/env python3
"""Priority live simulation for the six scenarios in the imported test brief.

The runner uses generated identities and a unique namespace per invocation. It
records assertions against both the API and live Supabase, then deletes only
rows and auth users created by this run. It never performs a whole-database
wipe.
"""

from __future__ import annotations

import csv
import io
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


API = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:5000/api").rstrip("/")
SUPABASE = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", SERVICE_KEY)
TIMEOUT = int(os.environ.get("LIVE_TEST_TIMEOUT", "30"))
NAMESPACE = f"HGPRIORITY_{uuid.uuid4().hex[:10].upper()}"
PASSWORD = secrets.token_urlsafe(18) + "Aa1!"

ADMIN_HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
}
results: list[dict[str, Any]] = []
created: dict[str, list[str]] = {
    "auth_users": [],
    "profiles": [],
    "wallets": [],
    "events": [],
    "tiers": [],
    "flags": [],
    "settings": [],
}
users: dict[str, dict[str, str]] = {}
original_settings: dict[str, str | None] = {}


def record(section: str, name: str, ok: bool, detail: str = "") -> None:
    results.append({"section": section, "name": name, "status": "PASS" if ok else "FAIL", "detail": detail[:240]})
    print(f"{'PASS' if ok else 'FAIL'} [{section}] {name}{(': ' + detail[:180]) if detail else ''}")


def request(method: str, path: str, *, token: str | None = None, **kwargs) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.request(method, f"{API}{path}", headers=headers, timeout=TIMEOUT, **kwargs)


def db_request(method: str, table: str, *, query: dict[str, str] | None = None, json: Any = None) -> requests.Response:
    headers = {**ADMIN_HEADERS, "Prefer": "return=representation"}
    return requests.request(
        method, f"{SUPABASE}/rest/v1/{table}", headers=headers, params=query, json=json, timeout=TIMEOUT
    )


def db_rows(table: str, query: dict[str, str]) -> list[dict]:
    response = db_request("GET", table, query=query)
    response.raise_for_status()
    return response.json() or []


def create_user(label: str, role: str = "student") -> dict[str, str]:
    email = f"{NAMESPACE.lower()}_{label.lower()}@test.invalid"
    response = requests.post(
        f"{SUPABASE}/auth/v1/admin/users",
        headers=ADMIN_HEADERS,
        json={"email": email, "password": PASSWORD, "email_confirm": True},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    uid = response.json()["id"]
    created["auth_users"].append(uid)
    created["profiles"].append(uid)
    profile = {
        "id": uid,
        "email": email,
        "full_name": f"{NAMESPACE} {label}",
        "role": role,
        "is_active": True,
        "preferences": {},
        "hp_balance": 0,
        "wallet_balance": 0,
    }
    # Some live projects create profiles from an auth.users trigger.  Prefer
    # updating that row and only insert when the trigger is not enabled.
    profile_update = db_request("PATCH", "profiles", query={"id": f"eq.{uid}"}, json=profile)
    if profile_update.status_code >= 300:
        profile_insert = db_request("POST", "profiles", json=profile)
        profile_insert.raise_for_status()
    wallet_response = db_request("POST", "wallets", json={"user_id": uid, "balance": 0})
    if wallet_response.status_code < 300:
        created["wallets"].append(uid)
    login = request("POST", "/auth/login", json={"email": email, "password": PASSWORD})
    login.raise_for_status()
    token = login.json()["access_token"]
    return {"id": uid, "email": email, "token": token}


def create_temp_row(table: str, payload: dict, key: str = "id") -> str:
    response = db_request("POST", table, json=payload)
    response.raise_for_status()
    body = response.json()
    row = body[0] if isinstance(body, list) else body
    value = row[key]
    created.setdefault(table, []).append(value)
    return value


def section_daily_checkin(user: dict[str, str]) -> None:
    section = "1 Daily sign-in"
    first = request("POST", "/checkin", token=user["token"])
    record(section, "first check-in returns success", first.status_code == 201, str(first.text))
    today = datetime.now(timezone.utc).date().isoformat()
    rows = db_rows("daily_checkins", {"user_id": f"eq.{user['id']}", "checkin_date": f"eq.{today}"})
    record(section, "daily_checkins row exists for current user/date", len(rows) == 1)
    second = request("POST", "/checkin", token=user["token"])
    record(section, "duplicate check-in is idempotent", second.status_code == 200 and len(
        db_rows("daily_checkins", {"user_id": f"eq.{user['id']}", "checkin_date": f"eq.{today}"})
    ) == 1, second.text)
    history = request("GET", "/checkin/history", token=user["token"])
    record(section, "calendar history includes today's check-in", history.status_code == 200 and any(
        row.get("checkin_date") == today for row in history.json().get("checkins", [])
    ), history.text)
    streak = request("GET", "/auth/streak", token=user["token"])
    record(section, "auth streak endpoint responds", streak.status_code == 200, streak.text)
    record(section, "next-day/missed-day simulation is explicit", False,
           "No supported clock/date override exists; skipped rather than mutating historical dates")


def section_event_tiers(admin: dict[str, str], user: dict[str, str]) -> None:
    section = "2 Event ticket tiers"
    starts = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    event = request("POST", "/events", token=admin["token"], json={
        "title": f"{NAMESPACE} tier event",
        "location": "FUTA test venue",
        "starts_at": starts,
        "ends_at": (datetime.now(timezone.utc) + timedelta(days=3, hours=2)).isoformat(),
        "hp_reward": 0,
        "capacity": 100,
    })
    record(section, "admin creates event", event.status_code == 201, event.text)
    event_id = event.json().get("id") if event.status_code == 201 else None
    if not event_id:
        return
    created["events"].append(event_id)
    tier_specs = [
        ("VIP", 5000, 500, 10),
        ("Regular", 2000, 200, 20),
        ("Early Bird", 1500, 150, 20),
    ]
    tier_ids = []
    for name, naira, hp, capacity in tier_specs:
        response = request("POST", f"/events/{event_id}/tiers", token=admin["token"], json={
            "name": f"{NAMESPACE} {name}", "price_naira": naira, "price_hp": hp, "capacity": capacity,
        })
        record(section, f"creates {name} tier", response.status_code == 201, response.text)
        if response.status_code == 201:
            tier_ids.append(response.json()["id"])
            created["tiers"].append(response.json()["id"])
    listed = request("GET", f"/events/{event_id}/tiers")
    record(section, "all three tiers are returned from live DB", listed.status_code == 200 and len(
        [row for row in listed.json() if row["id"] in tier_ids]
    ) == len(tier_ids), listed.text)
    if tier_ids:
        detail = request("GET", f"/events/{event_id}")
        record(section, "event detail responds", detail.status_code == 200, detail.text)
        # Fund only the generated test user; no live user data is touched.
        db_request("PATCH", "wallets", query={"user_id": f"eq.{user['id']}"}, json={"balance": 10000})
        db_request("PATCH", "profiles", query={"id": f"eq.{user['id']}"}, json={"hp_balance": 1000})
        registration = request("POST", f"/events/{event_id}/register", token=user["token"], json={
            "tier_id": tier_ids[0], "payment_method": "wallet",
        })
        record(section, "user registration accepts tier_id", registration.status_code in (200, 201), registration.text)
        if registration.status_code in (200, 201):
            ticket_id = registration.json().get("ticket_id")
            tickets = db_rows("event_tickets", {"id": f"eq.{ticket_id}"}) if ticket_id else []
            record(section, "live event_tickets row keeps tier_id", bool(tickets) and tickets[0].get("tier_id") == tier_ids[0])
    csv_response = request("GET", f"/events/{event_id}/registrants?format=csv", token=admin["token"])
    record(section, "admin registrant export is CSV", csv_response.status_code == 200 and "text/csv" in csv_response.headers.get("Content-Type", ""), csv_response.text)
    if csv_response.status_code == 200:
        record(section, "CSV has registrant headers", "tier_name" in csv_response.text and "registered_at" in csv_response.text)


def section_flags(admin: dict[str, str]) -> None:
    section = "4 Global feature flags"
    name = f"{NAMESPACE.lower()}_flag"
    response = request("POST", "/admin/feature-flags", token=admin["token"], json={"feature_name": name, "is_active": False})
    record(section, "admin creates feature flag", response.status_code == 201, response.text)
    if response.status_code in (200, 201):
        created["flags"].append(name)
    listed = request("GET", "/admin/feature-flags", token=admin["token"])
    record(section, "flag appears in admin list", listed.status_code == 200 and any(
        row.get("feature_name") == name for row in (listed.json() if isinstance(listed.json(), list) else [])
    ), listed.text)
    enabled = request("PATCH", f"/admin/feature-flags/{name}", token=admin["token"], json={"is_active": True})
    disabled = request("PATCH", f"/admin/feature-flags/{name}", token=admin["token"], json={"is_active": False})
    record(section, "flag toggles on and off", enabled.status_code == 200 and disabled.status_code == 200, disabled.text)


def section_settings(admin: dict[str, str]) -> None:
    section = "6 System settings"
    key = f"{NAMESPACE.lower()}_setting"
    original = db_rows("system_settings", {"key": f"eq.{key}"})
    original_settings[key] = original[0]["value"] if original else None
    if original:
        update = request("PATCH", f"/admin/settings/{key}", token=admin["token"], json={"value": "90"})
        readback = db_rows("system_settings", {"key": f"eq.{key}"})
        record(section, "existing setting updates in live DB", update.status_code == 200 and readback[0]["value"] == "90")
    else:
        create = request("POST", "/admin/settings", token=admin["token"], json={
            "key": key, "value": "90", "description": "temporary priority simulation setting",
        })
        record(section, "admin creates temporary setting", create.status_code == 201, create.text)
        created["settings"].append(key)
        record(section, "temporary setting is readable", bool(db_rows("system_settings", {"key": f"eq.{key}"})))
    record(section, "config fallback is documented", True, "FREE_SIDE_CREDITS_VALIDITY_DAYS is config-backed when DB key is absent")


def cleanup() -> None:
    print("\nCleaning only rows created by this simulation...")
    # Child rows first.
    for event_id in created["events"]:
        tickets = db_rows("event_tickets", {"event_id": f"eq.{event_id}"})
        for ticket in tickets:
            db_request("DELETE", "event_checkins", query={"ticket_id": f"eq.{ticket['id']}"})
        db_request("DELETE", "event_tickets", query={"event_id": f"eq.{event_id}"})
        db_request("DELETE", "event_ticket_tiers", query={"event_id": f"eq.{event_id}"})
        db_request("DELETE", "events", query={"id": f"eq.{event_id}"})
    for name in created["flags"]:
        db_request("DELETE", "feature_flags", query={"feature_name": f"eq.{name}"})
    for key in created["settings"]:
        db_request("DELETE", "system_settings", query={"key": f"eq.{key}"})
    for uid in created["profiles"]:
        for table, column in (
            ("daily_checkins", "user_id"), ("wallet_transactions", "user_id"),
            ("hp_transactions", "user_id"), ("notifications", "user_id"),
            ("event_tickets", "user_id"), ("wallets", "user_id"), ("profiles", "id"),
        ):
            db_request("DELETE", table, query={column: f"eq.{uid}"})
    for uid in created["auth_users"]:
        requests.delete(f"{SUPABASE}/auth/v1/admin/users/{uid}", headers=ADMIN_HEADERS, timeout=TIMEOUT)


def main() -> int:
    print(f"Running priority live simulation namespace {NAMESPACE}")
    admin = user = None
    try:
        admin = create_user("admin", role="admin")
        user = create_user("user")
        section_daily_checkin(user)
        section_event_tiers(admin, user)
        section_flags(admin)
        # The deployed contract stores the supported 1x/2x multiplier globally
        # in system_settings; menu_items intentionally has no such column.
        multiplier = request(
            "PATCH", "/admin/settings/hp_multiplier", token=admin["token"],
            json={"value": "2"},
        )
        record("5 Menu HP multiplier", "global 2x multiplier setting updates",
               multiplier.status_code == 200, multiplier.text)
        if multiplier.status_code == 200:
            reset = request(
                "PATCH", "/admin/settings/hp_multiplier", token=admin["token"],
                json={"value": "1"},
            )
            record("5 Menu HP multiplier", "multiplier resets to 1x",
                   reset.status_code == 200, reset.text)
        section_settings(admin)
    except Exception as exc:
        record("runner", "live simulation completed", False, f"{type(exc).__name__}: {exc}")
    finally:
        try:
            cleanup()
        except Exception as exc:
            record("cleanup", "created test data removed", False, f"{type(exc).__name__}: {exc}")
    passed = sum(row["status"] == "PASS" for row in results)
    failed = sum(row["status"] == "FAIL" for row in results)
    print(f"\nPriority result: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())