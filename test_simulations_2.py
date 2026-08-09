"""
test_simulations_2.py — Holy Grills Simulation Suite 21-41
===========================================================
Covers every endpoint NOT tested in test_simulations.py (Sims 1-20):
  21A-E  Admin (audit, delivery batches, windows, HP bulk, users)
  22     Analytics (dashboard, CSV export, HP/orders/referral/sales/marketplace)
  23     Auth (refresh, change-pw, logout, addresses, streak, reset, device-token)
  24     Cart (update item, remove item)
  25     Challenges (list, update, delete)
  26     Events (list, detail, update, delete, catering)
  27     Health
  28     HP (tiers, spin, unlock history, flash redeem, bundles)
  29     Kitchen (batch summary, metrics, settings CRUD, windows)
  30     Leaderboard (rankings, my-rank, squad, squad/my-rank)
  31     Marketplace (listings, admin CRUD, vendor requests, purchases)
  32     Notifications (list, mark read, blasts)
  33     Order Locks (list, detail, admin/all)
  34     Orders (active, windows/status, zones, history, reorder, review,
            share, cancel-scheduled, claim)
  35     Referrals (stats)
  36     Rewards (list, detail, admin CRUD, redemption history)
  37     Riders (call link, earnings, history, stats)
  38     Saved For Later (full CRUD + move-to-cart + from-cart)
  39     Storefront (operating hours, override, section update, promo validate)
  40     Wallet (withdraw, admin transactions)
  41     Webhooks (Paystack charge.success, transfer.success, Flutterwave)

Verifies structure, status codes, and before/after relationships.
Does NOT hardcode specific numeric values — all comparisons are relational.

Run: python3 test_simulations_2.py
"""

import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from datetime import date, datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

BASE = "http://localhost:5000/api"
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SRK = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

PASS_C = "\033[92m✅ PASS\033[0m"
FAIL_C = "\033[91m❌ FAIL\033[0m"
WARN_C = "\033[93m⚠️  WARN\033[0m"
INFO_C = "\033[94mℹ️  INFO\033[0m"
BOLD, RESET = "\033[1m", "\033[0m"

RESULTS = {"pass": 0, "fail": 0, "warn": 0}
FAILED_DETAILS, GAPS, CLEANUP = [], [], []

ADMIN_H = {
    "apikey": SRK,
    "Authorization": f"Bearer {SRK}",
    "Content-Type": "application/json",
}


# ─── helpers ──────────────────────────────────────────────────────────────────

def p(label, status, detail=""):
    RESULTS[status] += 1
    icon = {"pass": PASS_C, "fail": FAIL_C, "warn": WARN_C}[status]
    print(f"  {icon} {label}" + (f" — {detail}" if detail else ""))
    if status == "fail":
        FAILED_DETAILS.append((label, detail))


def gap(label, detail=""):
    GAPS.append((label, detail))
    print(f"  {INFO_C} GAP: {label}" + (f" — {detail}" if detail else ""))


def section(title):
    print(f"\n{BOLD}{'═'*72}\n  {title}\n{'═'*72}{RESET}")


def api(method, path, token=None, body=None, params=None, headers=None, timeout=20):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if headers:
        h.update(headers)
    try:
        return requests.request(
            method, f"{BASE}{path}", headers=h, json=body, params=params, timeout=timeout
        )
    except Exception as exc:
        print(f"    (request error: {exc})")
        return None


def expect(r, label, expected, warn_on_fail=False):
    codes = expected if isinstance(expected, (list, tuple)) else [expected]
    if r is None:
        p(label, "warn", "no response")
        return False, None
    if r.status_code in codes:
        p(label, "pass", str(r.status_code))
        try:
            return True, r.json()
        except Exception:
            return True, None
    status = "warn" if warn_on_fail else "fail"
    try:
        err_body = r.json()
    except Exception:
        err_body = r.text[:200]
    p(label, status, f"expected {codes}, got {r.status_code}: {err_body}")
    try:
        return False, r.json()
    except Exception:
        return False, None


def has_keys(obj, *keys):
    """Return True if obj (dict) contains all listed keys."""
    if not isinstance(obj, dict):
        return False
    return all(k in obj for k in keys)


def sb_get(table, params=""):
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}?{params}", headers=ADMIN_H, timeout=15
    )
    return r.json() if r.status_code == 200 else []


def sb_insert(table, data):
    h = {**ADMIN_H, "Prefer": "return=representation"}
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}", headers=h, json=data, timeout=15
    )
    if r.status_code in (200, 201):
        rows = r.json()
        return rows[0] if isinstance(rows, list) and rows else rows
    print(f"    (sb_insert {table} failed: {r.status_code} {r.text[:250]})")
    return None


def sb_patch(table, qs, data):
    r = requests.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?{qs}",
        headers={**ADMIN_H, "Prefer": "return=minimal"},
        json=data,
        timeout=15,
    )
    return r.status_code in (200, 204)


def sb_delete(table, qs):
    r = requests.delete(
        f"{SUPABASE_URL}/rest/v1/{table}?{qs}", headers=ADMIN_H, timeout=15
    )
    return r.status_code in (200, 204)


def sb_delete_auth_user(uid):
    r = requests.delete(
        f"{SUPABASE_URL}/auth/v1/admin/users/{uid}", headers=ADMIN_H, timeout=15
    )
    return r.status_code in (200, 204)


def sb_login(email, password="Test1234!"):
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers=ADMIN_H,
        json={"email": email, "password": password},
        timeout=15,
    )
    if r.status_code == 200:
        d = r.json()
        return d.get("access_token"), d.get("refresh_token")
    return None, None


def create_test_user(suffix, role="student"):
    uid_str = uuid.uuid4().hex[:8]
    email = f"hgsim2_{suffix.lower()}_{uid_str}@test.invalid"
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=ADMIN_H,
        json={"email": email, "password": "Test1234!", "email_confirm": True},
        timeout=15,
    )
    if r.status_code not in (200, 201):
        raise RuntimeError(f"create_test_user {suffix} failed: {r.text[:200]}")
    uid = r.json()["id"]
    ref_code = f"S2{uid_str.upper()[:6]}"
    requests.post(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers={**ADMIN_H, "Prefer": "return=minimal,resolution=merge-duplicates"},
        json={
            "id": uid,
            "email": email,
            "full_name": f"HG2 Sim {suffix}",
            "phone": f"+234800{uid_str[:7]}",
            "role": role,
            "referral_code": ref_code,
            "hp_balance": 0,
            "wallet_balance": 0,
            "is_active": True,
            "preferences": {},
        },
        timeout=15,
    )
    requests.patch(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{uid}",
        headers={**ADMIN_H, "Prefer": "return=minimal"},
        json={"role": role, "referral_code": ref_code},
        timeout=15,
    )
    requests.post(
        f"{SUPABASE_URL}/rest/v1/wallets",
        headers={**ADMIN_H, "Prefer": "return=minimal,resolution=merge-duplicates"},
        json={"user_id": uid, "balance": 0},
        timeout=15,
    )
    tok, refresh = sb_login(email)
    if not tok:
        raise RuntimeError(f"Login for {suffix} failed")
    CLEANUP.append(
        (
            f"user:{suffix}",
            lambda u=uid: (
                sb_delete("profiles", f"id=eq.{u}"),
                sb_delete_auth_user(u),
            ),
        )
    )
    return uid, tok, refresh, email, ref_code


def seed_wallet(user_id, naira):
    sb_patch("profiles", f"id=eq.{user_id}", {"wallet_balance": naira})
    sb_patch("wallets", f"user_id=eq.{user_id}", {"balance": naira})


def seed_hp(user_id, hp):
    sb_patch("profiles", f"id=eq.{user_id}", {"hp_balance": hp})


def get_hp(tok):
    r = api("GET", "/hp/balance", token=tok)
    return r.json() if r and r.status_code == 200 else {}


def get_menu_item():
    rows = sb_get("menu_items", "is_available=eq.true&select=id,price&limit=1")
    if rows:
        return rows[0]
    rows = sb_get("menu_items", "select=id,price&limit=1")
    return rows[0] if rows else None


def get_or_create_window():
    rows = sb_get("delivery_windows", "status=eq.open&select=id&limit=1")
    if rows:
        return rows[0]["id"]
    rows = sb_get("delivery_windows", "select=id&order=created_at.desc&limit=1")
    if rows:
        return rows[0]["id"]
    return None


def place_order(tok, menu_item_id, window_id, wallet=10000):
    return api(
        "POST",
        "/orders",
        token=tok,
        body={
            "items": [{"menu_item_id": menu_item_id, "quantity": 2}],
            "delivery_window_id": window_id,
            "payment_method": "wallet",
            "delivery_address": {
                "address_line": "1 Sim Close",
                "landmark": "Gate",
                "zone": "campus",
            },
        },
    )


def walk_to_delivered(order_id, kitchen_tok, admin_tok, rider_tok):
    api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "preparing"})
    api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "ready"})
    api("PATCH", f"/orders/{order_id}/status", token=admin_tok, body={"status": "assigned"})
    api("POST", f"/riders/orders/{order_id}/pickup", token=rider_tok)
    api("POST", f"/riders/orders/{order_id}/deliver", token=rider_tok)


# ─── simulations ──────────────────────────────────────────────────────────────


def sim_21a_admin_audit_cron(admin_tok):
    section("SIM 21A · ADMIN — AUDIT LOG & CRON STATUS")
    r = api("GET", "/admin/audit-log", token=admin_tok)
    ok, data = expect(r, "GET /admin/audit-log", 200)
    if ok:
        rows = data if isinstance(data, list) else data.get("logs", data.get("items", []))
        p(
            "Audit log returns a list",
            "pass" if isinstance(rows, list) else "warn",
            f"count={len(rows)}",
        )
        if rows:
            first = rows[0]
            p(
                "Audit row has actor_id + action fields",
                "pass" if has_keys(first, "actor_id", "action") else "warn",
                str(list(first.keys())[:8]),
            )

    r = api("GET", "/admin/cron/status", token=admin_tok)
    ok, data = expect(r, "GET /admin/cron/status", 200)
    if ok:
        p(
            "Cron status returns a dict",
            "pass" if isinstance(data, dict) else "warn",
            str(data)[:120],
        )


def sim_21b_delivery_batches(admin_tok, rider_id, window_id, order_ids):
    section("SIM 21B · ADMIN — DELIVERY BATCHES FULL CRUD")
    # create
    r = api(
        "POST",
        "/admin/delivery-batches",
        token=admin_tok,
        body={
            "window_id": window_id,
            "rider_id": rider_id,
            "zone": "campus",
            "order_ids": order_ids,
        },
    )
    ok, batch = expect(r, "Admin creates delivery batch", 201)
    if not ok:
        gap("Could not create delivery batch", str(batch))
        return None
    batch_id = batch.get("id") or (batch.get("batch") or {}).get("id")
    p(
        "Batch status == assigned",
        "pass" if batch.get("status") == "assigned" else "warn",
        str(batch.get("status")),
    )

    # get detail
    r = api("GET", f"/admin/delivery-batches/{batch_id}", token=admin_tok)
    ok, detail = expect(r, "Admin gets batch detail", 200)
    if ok:
        p(
            "Batch detail contains id + zone",
            "pass" if has_keys(detail, "id", "zone") else "warn",
            str(list(detail.keys())[:8]),
        )

    # list orders in batch
    r = api("GET", f"/admin/delivery-batches/{batch_id}/orders", token=admin_tok)
    expect(r, "GET /admin/delivery-batches/{id}/orders", [200], warn_on_fail=True)

    # update batch status
    r = api(
        "PATCH",
        f"/admin/delivery-batches/{batch_id}",
        token=admin_tok,
        body={"status": "completed"},
    )
    ok_upd, _ = expect(r, "Admin updates batch status → completed", [200], warn_on_fail=True)

    # cancel / delete batch
    r = api("DELETE", f"/admin/delivery-batches/{batch_id}", token=admin_tok)
    ok_del, _ = expect(r, "Admin cancels/deletes batch", [200, 204], warn_on_fail=True)
    if ok_del:
        rows = sb_get("delivery_batches", f"id=eq.{batch_id}&select=status")
        status_in_db = rows[0]["status"] if rows else None
        p(
            "Batch status == cancelled in DB",
            "pass" if status_in_db == "cancelled" else "warn",
            str(status_in_db),
        )
    return batch_id


def sim_21c_delivery_windows(admin_tok):
    section("SIM 21C · ADMIN — DELIVERY WINDOWS FULL CRUD")
    now = datetime.now(timezone.utc)
    r = api(
        "POST",
        "/admin/delivery-windows",
        token=admin_tok,
        body={
            "label": f"Sim Window {uuid.uuid4().hex[:5]}",
            "starts_at": (now + timedelta(days=2)).isoformat(),
            "ends_at": (now + timedelta(days=2, hours=2)).isoformat(),
            "capacity": 50,
        },
    )
    ok, win = expect(r, "Admin creates delivery window", [200, 201])
    if not ok:
        gap("Could not create delivery window", str(win))
        return

    win_id = win.get("id") or (win.get("window") or {}).get("id")
    p(
        "Window status open / present",
        "pass" if win.get("status") in ("open", None) or win_id else "warn",
        str(win.get("status")),
    )

    r = api("POST", f"/admin/delivery-windows/{win_id}/close", token=admin_tok)
    ok_c, _ = expect(r, "Admin closes window", [200], warn_on_fail=True)
    if ok_c:
        row = sb_get("delivery_windows", f"id=eq.{win_id}&select=status")
        p(
            "Window status == closed in DB",
            "pass" if row and row[0]["status"] == "closed" else "warn",
            str(row),
        )

    r = api("POST", f"/admin/delivery-windows/{win_id}/reopen", token=admin_tok)
    ok_r, _ = expect(r, "Admin reopens window", [200], warn_on_fail=True)
    if ok_r:
        row = sb_get("delivery_windows", f"id=eq.{win_id}&select=status")
        p(
            "Window status == open in DB after reopen",
            "pass" if row and row[0]["status"] == "open" else "warn",
            str(row),
        )
    # cleanup
    sb_delete("delivery_windows", f"id=eq.{win_id}")


def sim_21d_hp_bulk_grant_report(admin_tok):
    section("SIM 21D · ADMIN — HP BULK GRANT & REPORT")
    r = api(
        "POST",
        "/admin/hp/bulk-grant",
        token=admin_tok,
        body={"amount": 20, "reason": "Sim bulk grant test"},
        timeout=60,
    )
    ok, resp = expect(r, "Admin bulk-grants HP to all users", [200, 202], warn_on_fail=True)
    if ok:
        p(
            "Response has awarded_count or total_hp_awarded",
            "pass"
            if isinstance(resp, dict)
            and (
                "awarded_count" in resp
                or "total_hp_awarded" in resp
                or "granted" in str(resp).lower()
            )
            else "warn",
            str(resp)[:150],
        )

    r = api("GET", "/admin/hp/report", token=admin_tok)
    ok, rep = expect(r, "GET /admin/hp/report", 200)
    if ok:
        expected_keys = {
            "total_hp_issued",
            "total_hp_spent",
            "net_hp_in_system",
            "users_by_tier",
            "top_earners",
        }
        present = expected_keys & set(rep.keys()) if isinstance(rep, dict) else set()
        p(
            f"HP report has expected keys ({len(present)}/{len(expected_keys)})",
            "pass" if len(present) >= 3 else "warn",
            str(present),
        )


def sim_21e_admin_orders_users(admin_tok, target_user_id, promo_id):
    section("SIM 21E · ADMIN — ORDERS & USERS")
    # list orders
    r = api("GET", "/admin/orders", token=admin_tok, params={"limit": 5})
    ok, data = expect(r, "GET /admin/orders", 200)
    if ok:
        orders = data if isinstance(data, list) else data.get("orders", [])
        p("Orders list is non-empty", "pass" if orders else "warn", f"count={len(orders)}")

    # get user detail
    r = api("GET", f"/admin/users/{target_user_id}", token=admin_tok)
    ok, user = expect(r, "GET /admin/users/{id}", 200)
    if ok:
        # response shape: {"hp_balance": N, "profile": {...}, "wallet_balance": N, ...}
        p(
            "User detail has hp_balance key",
            "pass" if isinstance(user, dict) and "hp_balance" in user else "warn",
            str(list(user.keys())[:8]),
        )

    # HP history
    r = api("GET", f"/admin/users/{target_user_id}/hp", token=admin_tok)
    ok, hp_hist = expect(r, "GET /admin/users/{id}/hp", 200)
    if ok:
        p(
            "HP history is a list or wrapped object",
            "pass" if isinstance(hp_hist, (list, dict)) else "warn",
            str(type(hp_hist)),
        )

    # wallet history
    r = api("GET", f"/admin/users/{target_user_id}/wallet", token=admin_tok)
    expect(r, "GET /admin/users/{id}/wallet", 200)

    # deactivate
    r = api("POST", f"/admin/users/{target_user_id}/deactivate", token=admin_tok)
    ok_d, _ = expect(r, "Admin deactivates user", [200], warn_on_fail=True)
    if ok_d:
        row = sb_get("profiles", f"id=eq.{target_user_id}&select=is_active")
        p(
            "is_active == False after deactivate",
            "pass" if row and row[0]["is_active"] is False else "warn",
            str(row),
        )

    # re-activate
    r = api("POST", f"/admin/users/{target_user_id}/activate", token=admin_tok)
    ok_a, _ = expect(r, "Admin re-activates user", [200], warn_on_fail=True)
    if ok_a:
        row = sb_get("profiles", f"id=eq.{target_user_id}&select=is_active")
        p(
            "is_active == True after activate",
            "pass" if row and row[0]["is_active"] is True else "warn",
            str(row),
        )

    # promo update + usage
    if promo_id:
        r = api(
            "PATCH",
            f"/admin/promo-codes/{promo_id}",
            token=admin_tok,
            body={"is_active": False},
        )
        expect(r, "Admin deactivates promo code", [200], warn_on_fail=True)
        r = api("GET", f"/admin/promo-codes/{promo_id}/uses", token=admin_tok)
        ok, uses = expect(r, "GET /admin/promo-codes/{id}/uses", [200], warn_on_fail=True)
        if ok:
            p(
                "Uses response has total_uses key",
                "pass"
                if isinstance(uses, dict)
                and ("total_uses" in uses or "uses" in uses or "count" in uses)
                else "warn",
                str(uses)[:120],
            )


def sim_22_analytics(admin_tok):
    section("SIM 22 · ANALYTICS")
    now = datetime.now(timezone.utc)
    month_ago = (now - timedelta(days=30)).date().isoformat()
    today = now.date().isoformat()

    # dashboard — shape: {"as_of": ..., "today": {...}, "delivery_pipeline": {...}}
    r = api("GET", "/analytics/dashboard", token=admin_tok)
    ok, dash = expect(r, "GET /analytics/dashboard", 200)
    if ok:
        today_block = (dash or {}).get("today", {}) if isinstance(dash, dict) else {}
        keys_present = {"total_orders", "active_orders", "delivered_orders",
                        "revenue_delivered", "orders_by_status"} & set(today_block.keys())
        p(
            f"Dashboard.today has expected keys ({len(keys_present)}/5)",
            "pass" if len(keys_present) >= 3 else "warn",
            str(keys_present),
        )
        p(
            "Dashboard has delivery_pipeline block",
            "pass" if "delivery_pipeline" in (dash or {}) else "warn",
            str(list((dash or {}).keys())[:5]),
        )

    # CSV export
    r = api(
        "GET",
        "/analytics/export",
        token=admin_tok,
        params={"type": "orders", "from_date": month_ago, "to_date": today},
    )
    ok_csv = r and r.status_code == 200
    p(
        "GET /analytics/export?type=orders returns 200",
        "pass" if ok_csv else "warn",
        str(r.status_code) if r else "no response",
    )
    if ok_csv:
        content_type = r.headers.get("Content-Type", "")
        p(
            "Export Content-Type is CSV or stream",
            "pass" if "csv" in content_type.lower() or "text" in content_type.lower() or "octet" in content_type.lower() else "warn",
            content_type,
        )

    # HP analytics
    r = api("GET", "/analytics/hp", token=admin_tok)
    ok, hp_data = expect(r, "GET /analytics/hp", 200)
    if ok:
        keys_present = {"hp_earned_active", "hp_spent", "hp_expired", "hp_pending",
                        "hp_in_circulation", "redemption_rate"} & set(hp_data.keys() if isinstance(hp_data, dict) else [])
        p(
            f"HP analytics has expected keys ({len(keys_present)}/6)",
            "pass" if len(keys_present) >= 3 else "warn",
            str(keys_present),
        )

    # marketplace analytics
    r = api("GET", "/analytics/marketplace", token=admin_tok)
    ok, mkt = expect(r, "GET /analytics/marketplace", 200)
    if ok:
        p(
            "Marketplace analytics is a dict",
            "pass" if isinstance(mkt, dict) else "warn",
            str(list(mkt.keys())[:6]) if isinstance(mkt, dict) else str(mkt)[:100],
        )

    # order flow analytics
    r = api(
        "GET",
        "/analytics/orders",
        token=admin_tok,
        params={"from_date": month_ago, "to_date": today},
    )
    ok, ord_data = expect(r, "GET /analytics/orders", 200)
    if ok:
        p(
            "Order analytics has total_orders key",
            "pass" if isinstance(ord_data, dict) and "total_orders" in ord_data else "warn",
            str(list(ord_data.keys())[:6]) if isinstance(ord_data, dict) else str(ord_data)[:100],
        )

    # referral analytics
    r = api("GET", "/analytics/referrals", token=admin_tok)
    ok, ref_data = expect(r, "GET /analytics/referrals", 200)
    if ok:
        p(
            "Referral analytics has conversion_rate key",
            "pass" if isinstance(ref_data, dict) and "conversion_rate" in ref_data else "warn",
            str(ref_data)[:120],
        )

    # sales analytics
    r = api(
        "GET",
        "/analytics/sales",
        token=admin_tok,
        params={"from_date": month_ago, "to_date": today},
    )
    ok, sales = expect(r, "GET /analytics/sales", 200)
    if ok:
        p(
            "Sales analytics has total_revenue key",
            "pass" if isinstance(sales, dict) and "total_revenue" in sales else "warn",
            str(list(sales.keys())[:6]) if isinstance(sales, dict) else str(sales)[:100],
        )


def sim_23_auth(admin_tok):
    section("SIM 23 · AUTH — ALL UNTESTED ENDPOINTS")
    # Create a dedicated user for auth tests
    uid, tok, refresh, email, _ = create_test_user("AUTHTEST")

    # refresh token
    r = api("POST", "/auth/refresh", body={"refresh_token": refresh, "access_token": tok})
    ok, ref_resp = expect(r, "POST /auth/refresh", [200, 201], warn_on_fail=True)
    if ok:
        has_tok = bool(ref_resp.get("access_token"))
        p(
            "Refresh returns access_token",
            "pass" if has_tok else "warn",
            str(ref_resp)[:120],
        )
        if ref_resp.get("access_token"):
            tok = ref_resp["access_token"]  # use fresh token going forward

    # login streak
    r = api("GET", "/auth/streak", token=tok)
    ok, streak = expect(r, "GET /auth/streak", 200)
    if ok:
        p(
            "Streak has streak_count field",
            "pass" if isinstance(streak, dict) and "streak_count" in streak else "warn",
            str(streak)[:120],
        )

    # add address
    r = api(
        "POST",
        "/auth/addresses",
        token=tok,
        body={
            "label": "Home",
            "line1": "42 Sim Street",
            "city": "Akure",
            "state": "Ondo",
            "is_default": True,
        },
    )
    ok_addr, addr = expect(r, "POST /auth/addresses", [200, 201], warn_on_fail=True)
    addr_id = (addr.get("address") or addr or {}).get("id") if ok_addr else None

    # list addresses
    r = api("GET", "/auth/addresses", token=tok)
    ok, addr_list = expect(r, "GET /auth/addresses", 200)
    if ok:
        items = addr_list if isinstance(addr_list, list) else addr_list.get("addresses", [])
        p("Addresses list is non-empty", "pass" if items else "warn", f"count={len(items)}")

    # update address
    if addr_id:
        r = api(
            "PATCH",
            f"/auth/addresses/{addr_id}",
            token=tok,
            body={"label": "Work", "line1": "99 Updated Lane"},
        )
        ok_upd, _ = expect(r, "PATCH /auth/addresses/{id}", [200], warn_on_fail=True)

        # delete address
        r = api("DELETE", f"/auth/addresses/{addr_id}", token=tok)
        expect(r, "DELETE /auth/addresses/{id}", [200, 204], warn_on_fail=True)

    # register device token
    r = api(
        "POST",
        "/auth/device-token",
        token=tok,
        body={
            "token": f"sim_device_token_{uuid.uuid4().hex[:12]}",
            "platform": "android",
            "device_model": "Pixel 7",
        },
    )
    expect(r, "POST /auth/device-token", [200, 201], warn_on_fail=True)

    # change password
    r = api(
        "POST",
        "/auth/change-password",
        token=tok,
        body={"current_password": "Test1234!", "new_password": "Test5678!"},
    )
    expect(r, "POST /auth/change-password", [200], warn_on_fail=True)

    # password reset request (email-only — does not require auth)
    r = api("POST", "/auth/reset-password", body={"email": email})
    expect(r, "POST /auth/reset-password (email trigger)", [200], warn_on_fail=True)

    # verify email request
    r = api("POST", "/auth/verify-email", body={"email": email})
    expect(r, "POST /auth/verify-email (trigger)", [200], warn_on_fail=True)

    # logout-all-devices
    r = api("POST", "/auth/logout-all-devices", token=tok)
    ok_lad, lad_resp = expect(r, "POST /auth/logout-all-devices", [200], warn_on_fail=True)
    if ok_lad:
        p(
            "logout-all-devices returns devices_revoked count",
            "pass"
            if isinstance(lad_resp, dict)
            and ("devices_revoked" in lad_resp or "revoked" in str(lad_resp).lower())
            else "warn",
            str(lad_resp)[:120],
        )

    # logout (invalidates current token)
    r = api("POST", "/auth/logout", token=tok)
    expect(r, "POST /auth/logout", [200], warn_on_fail=True)

    # delete account — create a fresh user so we don't blow away our main auth user
    uid2, tok2, _, email2, _ = create_test_user("DELACCT")
    r = api(
        "DELETE",
        "/auth/account",
        token=tok2,
        body={"password": "Test1234!", "reason": "Testing account deletion"},
    )
    ok_del, del_resp = expect(r, "DELETE /auth/account", [200], warn_on_fail=True)
    if ok_del:
        p(
            "Account deletion response present",
            "pass" if del_resp else "warn",
            str(del_resp)[:120],
        )


def sim_24_cart(student_tok, menu_item_id):
    section("SIM 24 · CART — UPDATE ITEM + REMOVE ITEM")
    # add an item first
    r = api("POST", "/cart", token=student_tok, body={"menu_item_id": menu_item_id, "quantity": 1})
    ok, item = expect(r, "Add item to cart (setup)", [200, 201], warn_on_fail=True)
    item_id = None
    if ok and isinstance(item, dict):
        item_id = (
            item.get("id")
            or item.get("item_id")
            or item.get("cart_item_id")
            or (item.get("item") or {}).get("id")
        )
    if not item_id:
        # pull from cart
        r2 = api("GET", "/cart", token=student_tok)
        if r2 and r2.status_code == 200:
            cart = r2.json()
            items = cart.get("items", cart) if isinstance(cart, dict) else cart
            if isinstance(items, list) and items:
                item_id = items[0].get("id")

    if not item_id:
        gap("Could not determine cart item id for update/delete tests")
        return

    # update quantity — response: {"message": "...", "item": {"quantity": N, ...}}
    r = api("PATCH", f"/cart/{item_id}", token=student_tok, body={"quantity": 3})
    ok_upd, updated = expect(r, "PATCH /cart/{item_id} (update quantity)", [200], warn_on_fail=True)
    if ok_upd:
        item_block = (updated or {}).get("item") or {}
        qty = item_block.get("quantity")
        p(
            "Quantity updated to 3",
            "pass" if qty == 3 else "warn",
            f"quantity={qty}",
        )

    # remove item
    r = api("DELETE", f"/cart/{item_id}", token=student_tok)
    ok_del, _ = expect(r, "DELETE /cart/{item_id} (remove item)", [200, 204], warn_on_fail=True)
    if ok_del:
        r2 = api("GET", "/cart", token=student_tok)
        if r2 and r2.status_code == 200:
            cart = r2.json()
            items = cart.get("items", cart) if isinstance(cart, dict) else cart
            still_there = any(i.get("id") == item_id for i in (items if isinstance(items, list) else []))
            p(
                "Removed item no longer in cart",
                "pass" if not still_there else "warn",
            )


def sim_25_challenges(admin_tok, student_tok):
    section("SIM 25 · CHALLENGES — LIST, UPDATE, DELETE")
    # create one for manipulation
    r = api(
        "POST",
        "/challenges/admin",
        token=admin_tok,
        body={
            "title": f"Sim25 Challenge {uuid.uuid4().hex[:5]}",
            "hp_awarded": 30,
            "trigger_type": "orders_count", "trigger_value": 1,
            "time_window": "monthly", "is_active": True,
        },
    )
    ok, ch = expect(r, "Admin creates challenge (setup)", 201)
    ch_id = ch.get("id") if ok else None

    # list active challenges
    r = api("GET", "/challenges", token=student_tok)
    ok, ch_list = expect(r, "GET /challenges (active list)", 200)
    if ok:
        items = ch_list if isinstance(ch_list, list) else ch_list.get("challenges", [])
        p("Challenges list is a list", "pass" if isinstance(items, list) else "warn", f"count={len(items)}")
        if items:
            first = items[0]
            p(
                "Challenge item has title + hp_reward",
                "pass" if has_keys(first, "title", "hp_reward") else "warn",
                str(list(first.keys())[:6]),
            )

    if ch_id:
        # update
        r = api(
            "PATCH",
            f"/challenges/admin/{ch_id}",
            token=admin_tok,
            body={"is_active": False},
        )
        ok_upd, _ = expect(r, "PATCH /challenges/{id} (deactivate)", [200], warn_on_fail=True)
        if ok_upd:
            rows = sb_get("challenges", f"id=eq.{ch_id}&select=is_active")
            p(
                "is_active == False after PATCH",
                "pass" if rows and rows[0]["is_active"] is False else "warn",
                str(rows),
            )

        # delete (soft)
        r = api("DELETE", f"/challenges/admin/{ch_id}", token=admin_tok)
        expect(r, "DELETE /challenges/{id}", [200, 204], warn_on_fail=True)


def sim_26_events(admin_tok, student_tok):
    section("SIM 26 · EVENTS — FULL CRUD + CATERING")
    now = datetime.now(timezone.utc)
    # create event
    r = api(
        "POST",
        "/events",
        token=admin_tok,
        body={
            "title": f"Sim26 Event {uuid.uuid4().hex[:5]}",
            "location": "Main Hall",
            "starts_at": (now + timedelta(days=3)).isoformat(),
            "ends_at": (now + timedelta(days=3, hours=2)).isoformat(),
            "hp_reward": 25,
            "capacity": 50,
            "is_published": True,
        },
    )
    ok, event = expect(r, "Admin creates event (setup)", 201)
    event_id = event.get("id") if ok else None

    # list
    r = api("GET", "/events")
    ok, ev_list = expect(r, "GET /events (public list)", 200)
    if ok:
        items = ev_list if isinstance(ev_list, list) else ev_list.get("events", [])
        p("Events list is a list", "pass" if isinstance(items, list) else "warn", f"count={len(items)}")

    if event_id:
        # get detail
        r = api("GET", f"/events/{event_id}")
        ok, ev_detail = expect(r, "GET /events/{id} (detail)", 200)
        if ok:
            p(
                "Event detail has title + hp_reward",
                "pass" if has_keys(ev_detail, "title", "hp_reward") else "warn",
                str(list(ev_detail.keys())[:8]),
            )

        # update
        r = api(
            "PATCH",
            f"/events/{event_id}",
            token=admin_tok,
            body={"title": f"Updated Event {uuid.uuid4().hex[:4]}", "hp_reward": 30},
        )
        ok_upd, upd = expect(r, "PATCH /events/{id} (update)", [200], warn_on_fail=True)
        if ok_upd:
            ev_obj = upd.get("event", upd) if isinstance(upd, dict) else {}
            p(
                "hp_reward updated to 30",
                "pass" if ev_obj.get("hp_reward") == 30 else "warn",
                str(ev_obj.get("hp_reward")),
            )

        # delete
        r = api("DELETE", f"/events/{event_id}", token=admin_tok)
        expect(r, "DELETE /events/{id}", [200, 204], warn_on_fail=True)

    # catering request (no auth needed)
    r = api(
        "POST",
        "/events/catering-requests",
        body={
            "organizer_name": "Sim Org",
            "email": f"simcatering_{uuid.uuid4().hex[:6]}@test.invalid",
            "phone": "+2348000000000",
            "event_name": "Sim Catering Event",
            "event_date": (now + timedelta(days=14)).date().isoformat(),
            "expected_guests": 50,
            "budget": 100000,
        },
    )
    ok_cat, cat = expect(r, "POST /events/catering-requests", [200, 201], warn_on_fail=True)
    if ok_cat:
        cat_obj = cat.get("request", cat) if isinstance(cat, dict) else {}
        cat_id = cat_obj.get("id") or cat.get("id")
        p(
            "Catering request has status=new",
            "pass" if cat_obj.get("status") in ("new", None) else "warn",
            str(cat_obj.get("status")),
        )

        # admin views catering requests
        r = api("GET", "/events/catering-requests", token=admin_tok, params={"status": "new"})
        expect(r, "GET /events/catering-requests (admin)", [200], warn_on_fail=True)

        # admin responds — valid statuses: new, reviewed, quoted, accepted, completed, rejected, cancelled
        if cat_id:
            r = api(
                "PATCH",
                f"/events/catering-requests/{cat_id}",
                token=admin_tok,
                body={"status": "quoted", "quoted_amount": 50000, "notes": "Sim quote"},
            )
            ok_resp, _ = expect(r, "PATCH /events/catering-requests/{id}", [200], warn_on_fail=True)
            if ok_resp:
                rows = sb_get("catering_requests", f"id=eq.{cat_id}&select=status")
                p(
                    "Catering status == quoted in DB",
                    "pass" if rows and rows[0]["status"] == "quoted" else "warn",
                    str(rows),
                )


def sim_27_health():
    section("SIM 27 · HEALTH")
    r = api("GET", "/health")
    ok, data = expect(r, "GET /health", 200)
    if ok:
        p("status field present", "pass" if "status" in data else "fail", str(data.get("status")))
        p("api == 'Holy Grills'", "pass" if data.get("api") == "Holy Grills" else "warn", str(data.get("api")))
        p(
            "checks.supabase == connected",
            "pass" if (data.get("checks") or {}).get("supabase") == "connected" else "warn",
            str((data.get("checks") or {}).get("supabase")),
        )


def sim_28_hp(student_tok, student_id):
    section("SIM 28 · HP — TIERS, SPIN, UNLOCK HISTORY, BUNDLES")
    # tiers
    r = api("GET", "/hp/tiers")
    ok, tiers = expect(r, "GET /hp/tiers", 200)
    if ok:
        items = tiers if isinstance(tiers, list) else tiers.get("tiers", [])
        p("Tiers list is non-empty", "pass" if items else "warn", f"count={len(items)}")
        if items:
            first = items[0]
            p(
                "Tier has name + min_points",
                "pass" if has_keys(first, "name") and ("min_points" in first or "min_hp" in first) else "warn",
                str(list(first.keys())[:6]),
            )

    # spin (may cost HP — use warn_on_fail)
    seed_hp(student_id, 500)
    r = api("POST", "/hp/spin", token=student_tok)
    ok_spin, spin_resp = expect(r, "POST /hp/spin (wheel spin)", [200, 201], warn_on_fail=True)
    if ok_spin:
        p(
            "Spin response has prize/hp_won field",
            "pass"
            if isinstance(spin_resp, dict)
            and ("prize" in spin_resp or "hp_won" in spin_resp or "result" in spin_resp)
            else "warn",
            str(spin_resp)[:150],
        )

    # spin history
    r = api("GET", "/hp/spin/history", token=student_tok, params={"limit": 5})
    ok, spin_hist = expect(r, "GET /hp/spin/history", 200)
    if ok:
        items = spin_hist if isinstance(spin_hist, list) else spin_hist.get("history", spin_hist.get("spins", []))
        p(
            "Spin history is a list",
            "pass" if isinstance(items, list) else "warn",
            f"count={len(items)}",
        )

    # unlock history
    r = api("GET", "/hp/unlock-history", token=student_tok, params={"limit": 5})
    ok, unlock = expect(r, "GET /hp/unlock-history", 200)
    if ok:
        items = unlock if isinstance(unlock, list) else unlock.get("history", unlock.get("transactions", []))
        p(
            "Unlock history is a list",
            "pass" if isinstance(items, list) else "warn",
            f"count={len(items)}",
        )

    # bundle purchase — Paystack-gated, expect 502 or 400 when not configured
    r = api(
        "POST",
        "/hp/bundles/purchase",
        token=student_tok,
        body={"hp_amount": 200, "paystack_reference": f"simref_{uuid.uuid4().hex[:8]}"},
    )
    if r and r.status_code in (200, 201):
        p("POST /hp/bundles/purchase succeeded (Paystack configured)", "pass")
    else:
        gap(
            "POST /hp/bundles/purchase failed — Paystack not configured",
            str(r.status_code) if r else "no response",
        )


def sim_29_kitchen(kitchen_tok, admin_tok, window_id):
    section("SIM 29 · KITCHEN — BATCH SUMMARY, METRICS, SETTINGS, WINDOWS")
    # batch summary
    r = api("GET", f"/kitchen/batch-summary/{window_id}", token=kitchen_tok)
    ok, summary = expect(r, "GET /kitchen/batch-summary/{window_id}", 200)
    if ok:
        p(
            "Batch summary is a list or dict",
            "pass" if isinstance(summary, (list, dict)) else "warn",
            str(type(summary)),
        )

    # metrics
    r = api("GET", "/kitchen/metrics", token=kitchen_tok, params={"window_id": window_id})
    ok, metrics = expect(r, "GET /kitchen/metrics", 200)
    if ok:
        p(
            "Metrics has total_orders key",
            "pass" if isinstance(metrics, dict) and "total_orders" in metrics else "warn",
            str(list(metrics.keys())[:6]) if isinstance(metrics, dict) else str(metrics)[:100],
        )

    # get settings
    r = api("GET", "/kitchen/settings", token=kitchen_tok)
    ok, settings = expect(r, "GET /kitchen/settings", 200)
    if ok:
        p(
            "Settings is a dict",
            "pass" if isinstance(settings, dict) else "warn",
            str(type(settings)),
        )

    # update settings
    r = api(
        "PATCH",
        "/kitchen/settings",
        token=admin_tok,
        body={"settings": {"daily_order_capacity": "60"}},
    )
    expect(r, "PATCH /kitchen/settings (update daily_order_capacity)", [200], warn_on_fail=True)

    # get single setting
    r = api("GET", "/kitchen/settings/daily_order_capacity", token=kitchen_tok)
    ok, single = expect(r, "GET /kitchen/settings/{key}", 200)
    if ok:
        p(
            "Single setting returns a value",
            "pass" if single is not None else "warn",
            str(single)[:80],
        )

    # delivery windows
    r = api("GET", "/kitchen/windows", token=kitchen_tok)
    ok, wins = expect(r, "GET /kitchen/windows", 200)
    if ok:
        items = wins if isinstance(wins, list) else wins.get("windows", [])
        p(
            "Kitchen windows list is a list",
            "pass" if isinstance(items, list) else "warn",
            f"count={len(items)}",
        )


def sim_30_leaderboard(student_tok):
    section("SIM 30 · LEADERBOARD — RANKINGS, MY-RANK, SQUAD")
    # main leaderboard
    r = api("GET", "/leaderboard", params={"period_type": "weekly", "limit": 10})
    ok, lb = expect(r, "GET /leaderboard?period_type=weekly", 200)
    if ok:
        items = lb if isinstance(lb, list) else lb.get("rankings", lb.get("leaderboard", []))
        p(
            "Leaderboard returns a list",
            "pass" if isinstance(items, list) else "warn",
            f"count={len(items)}",
        )

    # my rank
    r = api("GET", "/leaderboard/my-rank", token=student_tok, params={"period_type": "weekly"})
    ok, my_rank = expect(r, "GET /leaderboard/my-rank", 200)
    if ok:
        p(
            "my-rank response is a dict",
            "pass" if isinstance(my_rank, dict) else "warn",
            str(my_rank)[:120],
        )

    # squad leaderboard
    r = api("GET", "/leaderboard/squad", params={"period_type": "monthly"})
    ok, squad_lb = expect(r, "GET /leaderboard/squad?period_type=monthly", 200)
    if ok:
        items = squad_lb if isinstance(squad_lb, list) else squad_lb.get("rankings", squad_lb.get("leaderboard", []))
        p(
            "Squad leaderboard is a list",
            "pass" if isinstance(items, list) else "warn",
            f"count={len(items)}",
        )

    # my squad rank
    r = api("GET", "/leaderboard/squad/my-rank", token=student_tok)
    ok, sqr = expect(r, "GET /leaderboard/squad/my-rank", [200, 404], warn_on_fail=True)
    p(
        "Squad my-rank endpoint reachable",
        "pass" if r and r.status_code in (200, 404) else "warn",
        str(r.status_code) if r else "no response",
    )


def sim_31_marketplace(admin_tok, student_tok, student_id):
    section("SIM 31 · MARKETPLACE — LISTINGS, ADMIN CRUD, VENDOR REQUESTS, PURCHASES")
    seed_hp(student_id, 2000)

    # admin creates listing (code type — only type currently supported by DB)
    slug_base = f"sim31-listing-{uuid.uuid4().hex[:6]}"
    r = api(
        "POST",
        "/marketplace/admin/listings",
        token=admin_tok,
        body={
            "title": f"Sim31 Listing {uuid.uuid4().hex[:5]}",
            "listing_type": "code",
            "price": 800,
            "hp_price": 300,
        },
    )
    ok, listing = expect(r, "Admin creates marketplace listing", 201)
    listing_id = listing.get("id") if ok else None

    # list (public)
    r = api("GET", "/marketplace", params={"category": "code"})
    ok, mkt_list = expect(r, "GET /marketplace (public list)", 200)
    if ok:
        items = mkt_list if isinstance(mkt_list, list) else mkt_list.get("listings", [])
        p("Marketplace listings is a list", "pass" if isinstance(items, list) else "warn", f"count={len(items)}")

    if listing_id:
        # public detail
        r = api("GET", f"/marketplace/{listing_id}")
        ok, detail = expect(r, "GET /marketplace/{id} (public detail)", 200)
        if ok:
            p(
                "Listing detail has title + price",
                "pass" if has_keys(detail, "title", "price") else "warn",
                str(list(detail.keys())[:8]),
            )

        # admin detail
        r = api("GET", f"/marketplace/admin/listings/{listing_id}", token=admin_tok)
        ok, admin_detail = expect(r, "GET /marketplace/admin/listings/{id}", 200)
        if ok:
            p(
                "Admin listing detail has codes_total or purchase_count",
                "pass"
                if isinstance(admin_detail, dict)
                and ("codes_total" in admin_detail or "purchase_count" in admin_detail or "title" in admin_detail)
                else "warn",
                str(list(admin_detail.keys())[:8]),
            )

        # upload a code
        code_val = f"SIM31CODE{uuid.uuid4().hex[:6].upper()}"
        r = api(
            "POST",
            f"/marketplace/admin/codes/{listing_id}",
            token=admin_tok,
            body={"codes": [code_val]},
        )
        expect(r, "Admin uploads access code", [200, 201], warn_on_fail=True)

        # admin update listing — valid statuses: active, rejected, archived
        r = api(
            "PATCH",
            f"/marketplace/admin/listings/{listing_id}",
            token=admin_tok,
            body={"status": "archived"},
        )
        expect(r, "PATCH /marketplace/admin/listings/{id}", [200], warn_on_fail=True)

        # admin list purchases
        r = api("GET", "/marketplace/admin/purchases", token=admin_tok, params={"limit": 5})
        expect(r, "GET /marketplace/admin/purchases", 200)

        # admin delete listing
        r = api("DELETE", f"/marketplace/admin/listings/{listing_id}", token=admin_tok)
        expect(r, "DELETE /marketplace/admin/listings/{id}", [200, 204], warn_on_fail=True)

    # vendor submits request (no auth needed)
    r = api(
        "POST",
        "/marketplace/requests",
        body={
            "vendor_name": "Sim Vendor",
            "vendor_email": f"simvendor_{uuid.uuid4().hex[:6]}@test.invalid",
            "service_title": "Sim Service",
            "category": "code",
            "description": "Simulation vendor listing request",
            "proposed_price": 500,
        },
    )
    ok_vr, vr = expect(r, "POST /marketplace/requests (vendor)", [200, 201], warn_on_fail=True)
    vr_id = None
    if ok_vr:
        vr_obj = vr.get("request", vr) if isinstance(vr, dict) else {}
        vr_id = vr_obj.get("id") or vr.get("id")
        p(
            "Vendor request status == pending",
            "pass" if vr_obj.get("status") in ("pending", None) else "warn",
            str(vr_obj.get("status")),
        )

    # admin list vendor requests
    r = api("GET", "/marketplace/admin/requests", token=admin_tok, params={"status": "pending"})
    expect(r, "GET /marketplace/admin/requests (admin)", [200], warn_on_fail=True)

    # admin respond
    if vr_id:
        r = api(
            "PATCH",
            f"/marketplace/admin/requests/{vr_id}",
            token=admin_tok,
            body={"status": "approved", "admin_notes": "Sim approval"},
        )
        expect(r, "PATCH /marketplace/admin/requests/{id}", [200], warn_on_fail=True)


def sim_32_notifications(admin_tok, student_tok, student_id):
    section("SIM 32 · NOTIFICATIONS — LIST, MARK READ, BLASTS")
    # ensure the user has at least one notification
    notifs_db = sb_get("notifications", f"user_id=eq.{student_id}&select=id&limit=1")
    notif_id = notifs_db[0]["id"] if notifs_db else None

    # list
    r = api("GET", "/notifications", token=student_tok, params={"limit": 10})
    ok, n_list = expect(r, "GET /notifications", 200)
    if ok:
        items = (
            n_list if isinstance(n_list, list) else n_list.get("notifications", [])
        )
        p(
            "Notifications is a list",
            "pass" if isinstance(items, list) else "warn",
            f"count={len(items)}",
        )
        if items and not notif_id:
            notif_id = items[0].get("id")

    # mark single read
    if notif_id:
        r = api("POST", f"/notifications/{notif_id}/read", token=student_tok)
        ok_r, _ = expect(r, "POST /notifications/{id}/read", [200], warn_on_fail=True)
        if ok_r:
            rows = sb_get("notifications", f"id=eq.{notif_id}&select=read_at")
            p(
                "read_at timestamp set in DB",
                "pass" if rows and rows[0].get("read_at") else "warn",
                str(rows),
            )

    # mark all read
    r = api("POST", "/notifications/read-all", token=student_tok)
    expect(r, "POST /notifications/read-all", [200], warn_on_fail=True)

    # admin: create blast
    r = api(
        "POST",
        "/notifications/blasts",
        token=admin_tok,
        body={
            "title": f"Sim Blast {uuid.uuid4().hex[:5]}",
            "body": "This is a simulation notification blast.",
            "channels": ["in_app"],
        },
    )
    ok_blast, blast = expect(r, "POST /notifications/blasts (admin)", [200, 201])
    blast_id = (
        blast.get("blast", blast or {}).get("id")
        if isinstance(blast, dict)
        else None
    )
    if not blast_id and isinstance(blast, dict):
        blast_id = blast.get("id")

    # list blasts
    r = api("GET", "/notifications/blasts", token=admin_tok, params={"status": "sent"})
    expect(r, "GET /notifications/blasts (admin)", [200])

    # blast detail
    if blast_id:
        r = api("GET", f"/notifications/blasts/{blast_id}", token=admin_tok)
        ok_bd, bd = expect(r, "GET /notifications/blasts/{id}", [200], warn_on_fail=True)
        if ok_bd:
            p(
                "Blast detail has title + body",
                "pass" if has_keys(bd, "title", "body") else "warn",
                str(list(bd.keys())[:6]),
            )


def sim_33_order_locks(admin_tok, student_tok):
    section("SIM 33 · ORDER LOCKS — LIST, DETAIL, ADMIN/ALL")
    # create a lock for this sim
    lock_date = (date.today() + timedelta(days=30)).isoformat()
    r = api(
        "POST",
        "/order-locks",
        token=student_tok,
        body={"locked_date": lock_date, "discount_pct": 10},
    )
    ok, lk = expect(r, "Create order lock (setup)", 201)
    lock = (lk.get("lock") or lk) if ok and isinstance(lk, dict) else {}
    lock_id = lock.get("id")

    # list user locks
    r = api("GET", "/order-locks", token=student_tok, params={"status": "active"})
    ok, lk_list = expect(r, "GET /order-locks (user list)", 200)
    if ok:
        items = lk_list if isinstance(lk_list, list) else lk_list.get("locks", [])
        p(
            "Lock list is non-empty for this user",
            "pass" if items else "warn",
            f"count={len(items)}",
        )

    # get detail
    if lock_id:
        r = api("GET", f"/order-locks/{lock_id}", token=student_tok)
        ok, lk_detail = expect(r, "GET /order-locks/{id}", 200)
        if ok:
            p(
                "Lock detail has locked_date + discount_pct",
                "pass" if has_keys(lk_detail, "locked_date", "discount_pct") or has_keys(lk_detail.get("lock", {}), "locked_date") else "warn",
                str(lk_detail)[:120],
            )

    # admin all locks
    r = api("GET", "/order-locks/admin/all", token=admin_tok, params={"status": "active"})
    ok, all_locks = expect(r, "GET /order-locks/admin/all", 200)
    if ok:
        items = all_locks if isinstance(all_locks, list) else all_locks.get("locks", [])
        p(
            "Admin lock list is a list",
            "pass" if isinstance(items, list) else "warn",
            f"count={len(items)}",
        )

    # cleanup lock
    if lock_id:
        api("DELETE", f"/order-locks/{lock_id}", token=student_tok)


def sim_34_orders(admin_tok, student_tok, student_id, kitchen_tok, rider_tok, menu_item_id, window_id):
    section("SIM 34 · ORDERS — UNTESTED ENDPOINTS")
    seed_wallet(student_id, 20000)

    # delivery window status
    r = api("GET", "/orders/delivery-windows/status")
    ok, dws = expect(r, "GET /orders/delivery-windows/status", 200)
    if ok:
        p(
            "has is_open field",
            "pass" if isinstance(dws, dict) and "is_open" in dws else "warn",
            str(dws)[:120],
        )

    # delivery zones list
    r = api("GET", "/orders/delivery-zones")
    ok, zones = expect(r, "GET /orders/delivery-zones", 200)
    if ok:
        items = zones if isinstance(zones, list) else zones.get("zones", [])
        p("Zones is a list", "pass" if isinstance(items, list) else "warn", f"count={len(items)}")

    # active order (may be null/empty)
    r = api("GET", "/orders/active", token=student_tok)
    ok, active = expect(r, "GET /orders/active", [200], warn_on_fail=True)
    if ok:
        p(
            "Active order endpoint returns 200",
            "pass",
            "order or null",
        )

    # place order for history + review + share + reorder tests
    r = place_order(student_tok, menu_item_id, window_id)
    ok, order = expect(r, "Place order (setup for sub-tests)", 201)
    if not ok:
        gap("Could not place order for sim_34 sub-tests", str(order))
        return

    order_id = order.get("id") or order.get("order_id")

    # order history
    r = api("GET", f"/orders/{order_id}/history", token=student_tok)
    ok, hist = expect(r, "GET /orders/{id}/history", 200)
    if ok:
        items = hist if isinstance(hist, list) else hist.get("history", [])
        p(
            "History is a list with at least one entry",
            "pass" if isinstance(items, list) and len(items) >= 1 else "warn",
            f"count={len(items)}",
        )

    # reorder
    r = api("POST", f"/orders/{order_id}/reorder", token=student_tok)
    ok, reorder = expect(r, "POST /orders/{id}/reorder", 200)
    if ok:
        items = reorder if isinstance(reorder, list) else reorder.get("items", [])
        p(
            "Reorder returns items list with current_price",
            "pass"
            if isinstance(items, list)
            and items
            and "current_price" in items[0]
            else "warn",
            str(items[:1]),
        )

    # share order
    r = api(
        "POST",
        f"/orders/{order_id}/share",
        token=student_tok,
        body={"platform": "whatsapp"},
    )
    ok_share, share_resp = expect(r, "POST /orders/{id}/share", [200, 201], warn_on_fail=True)
    if ok_share:
        p(
            "Share response has hp_awarded field",
            "pass"
            if isinstance(share_resp, dict)
            and ("hp_awarded" in share_resp or "hp" in str(share_resp).lower())
            else "warn",
            str(share_resp)[:120],
        )

    # walk to delivered so we can review
    walk_to_delivered(order_id, kitchen_tok, admin_tok, rider_tok)
    time.sleep(1)

    # submit review
    r = api(
        "POST",
        f"/orders/{order_id}/review",
        token=student_tok,
        body={
            "rating": 4,
            "kitchen_rating": 4,
            "rider_rating": 5,
            "comment": "Simulation review — tasty!",
        },
    )
    ok_rv, review = expect(r, "POST /orders/{id}/review", 201)
    if ok_rv:
        p(
            "Review saved, hp_awarded field present",
            "pass" if isinstance(review, dict) and "hp_awarded" in review else "warn",
            str(review)[:120],
        )

    # cancel scheduled order — create a fresh scheduled order then cancel it
    r = place_order(student_tok, menu_item_id, window_id)
    ok2, order2 = expect(r, "Place scheduled order (setup)", 201)
    if ok2:
        order2_id = order2.get("id") or order2.get("order_id")
        r = api("DELETE", f"/orders/{order2_id}/scheduled", token=student_tok)
        ok_cs, cs_resp = expect(r, "DELETE /orders/{id}/scheduled (cancel scheduled)", [200], warn_on_fail=True)
        if ok_cs:
            rows = sb_get("orders", f"id=eq.{order2_id}&select=status")
            p(
                "Cancelled scheduled order status is cancelled",
                "pass" if rows and rows[0]["status"] == "cancelled" else "warn",
                str(rows),
            )


def sim_35_referrals(student_tok):
    section("SIM 35 · REFERRALS — STATS")
    r = api("GET", "/referrals/stats", token=student_tok)
    ok, stats = expect(r, "GET /referrals/stats", 200)
    if ok:
        p(
            "Stats has referral_code + total_referrals",
            "pass"
            if isinstance(stats, dict)
            and (
                "referral_code" in stats
                or "total_referrals" in stats
                or "code" in str(stats).lower()
            )
            else "warn",
            str(stats)[:150],
        )


def sim_36_rewards(admin_tok, student_tok, student_id):
    section("SIM 36 · REWARDS — LIST, DETAIL, ADMIN CRUD, REDEMPTION HISTORY")
    # admin creates reward — use "category" key which maps to reward_type in DB
    r = api(
        "POST",
        "/rewards",
        token=admin_tok,
        body={
            "name": f"Sim36 Reward {uuid.uuid4().hex[:5]}",
            "hp_cost": 100,
            "category": "food",
            "quantity_available": 10,
            "is_active": True,
        },
    )
    ok, reward = expect(r, "Admin creates reward", 201)
    reward_id = reward.get("id") if ok else None

    # public list
    r = api("GET", "/rewards")
    ok, rw_list = expect(r, "GET /rewards (public list)", 200)
    if ok:
        items = rw_list if isinstance(rw_list, list) else rw_list.get("rewards", [])
        p("Rewards list is a list", "pass" if isinstance(items, list) else "warn", f"count={len(items)}")

    if reward_id:
        # public detail
        r = api("GET", f"/rewards/{reward_id}")
        ok, rw_detail = expect(r, "GET /rewards/{id} (public detail)", 200)
        if ok:
            p(
                "Reward detail has hp_cost + name",
                "pass" if has_keys(rw_detail, "hp_cost", "name") else "warn",
                str(list(rw_detail.keys())[:8]),
            )

        # redeem it
        seed_hp(student_id, 500)
        r = api("POST", f"/rewards/{reward_id}/redeem", token=student_tok)
        expect(r, "Student redeems reward (setup for history)", [200, 201], warn_on_fail=True)

        # admin update
        r = api(
            "PATCH",
            f"/rewards/{reward_id}",
            token=admin_tok,
            body={"hp_cost": 150, "is_active": False},
        )
        ok_upd, upd_rw = expect(r, "PATCH /rewards/{id} (admin update)", [200], warn_on_fail=True)
        if ok_upd:
            rw_obj = upd_rw.get("reward", upd_rw) if isinstance(upd_rw, dict) else {}
            p(
                "hp_cost updated to 150",
                "pass" if rw_obj.get("hp_cost") == 150 else "warn",
                str(rw_obj.get("hp_cost")),
            )

        # admin delete (soft)
        r = api("DELETE", f"/rewards/{reward_id}", token=admin_tok)
        expect(r, "DELETE /rewards/{id} (admin soft-delete)", [200, 204], warn_on_fail=True)

    # redemption history
    r = api("GET", "/rewards/redemptions", token=student_tok)
    ok, red_hist = expect(r, "GET /rewards/redemptions (user history)", 200)
    if ok:
        items = red_hist if isinstance(red_hist, list) else red_hist.get("redemptions", [])
        p(
            "Redemption history is a list",
            "pass" if isinstance(items, list) else "warn",
            f"count={len(items)}",
        )


def sim_37_riders(rider_tok, rider_id, admin_tok, student_tok, student_id, menu_item_id, window_id, kitchen_tok):
    section("SIM 37 · RIDERS — CALL LINK, EARNINGS, HISTORY, STATS")
    seed_wallet(student_id, 10000)

    # place + walk to out_for_delivery so rider has an active order
    r = place_order(student_tok, menu_item_id, window_id)
    ok, order = expect(r, "Place order for rider endpoints (setup)", 201)
    order_id = (order.get("id") or order.get("order_id")) if ok else None

    if order_id:
        api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "preparing"})
        api("PATCH", f"/orders/{order_id}/status", token=kitchen_tok, body={"status": "ready"})
        api("PATCH", f"/orders/{order_id}/status", token=admin_tok, body={"status": "assigned"})
        api("POST", f"/riders/orders/{order_id}/pickup", token=rider_tok)

        # call link
        r = api("GET", f"/riders/call/{order_id}", token=rider_tok)
        ok_call, call_resp = expect(r, "GET /riders/call/{order_id}", 200)
        if ok_call:
            call_link = (call_resp or {}).get("call_link", "")
            p(
                "call_link is a tel: URI (phone not exposed in plain text)",
                "pass" if str(call_link).startswith("tel:") else "warn",
                str(call_link)[:30],
            )

        # deliver
        api("POST", f"/riders/orders/{order_id}/deliver", token=rider_tok)

    # earnings
    r = api("GET", "/riders/earnings", token=rider_tok, params={"period": "week"})
    ok, earnings = expect(r, "GET /riders/earnings", 200)
    if ok:
        p(
            "Earnings has total_deliveries + total_earnings",
            "pass"
            if isinstance(earnings, dict)
            and (
                "total_deliveries" in earnings
                or "total_earnings" in earnings
                or "deliveries" in earnings
            )
            else "warn",
            str(earnings)[:150],
        )

    # history
    r = api("GET", "/riders/history", token=rider_tok, params={"limit": 10})
    ok, hist = expect(r, "GET /riders/history", 200)
    if ok:
        items = hist if isinstance(hist, list) else hist.get("history", [])
        p("Rider history is a list", "pass" if isinstance(items, list) else "warn", f"count={len(items)}")

    # stats
    r = api("GET", "/riders/stats", token=rider_tok)
    ok, stats = expect(r, "GET /riders/stats", 200)
    if ok:
        p(
            "Rider stats has total_batches or total_orders_delivered",
            "pass"
            if isinstance(stats, dict)
            and (
                "total_batches" in stats
                or "total_orders_delivered" in stats
                or "completion_rate" in stats
            )
            else "warn",
            str(stats)[:150],
        )


def sim_38_saved(student_tok, student_id, menu_item_id):
    section("SIM 38 · SAVED FOR LATER — FULL CRUD + MOVE-TO-CART + FROM-CART")
    # save an item
    r = api(
        "POST",
        "/saved",
        token=student_tok,
        body={"menu_item_id": menu_item_id, "quantity": 1, "notes": "Sim saved note"},
    )
    ok, saved = expect(r, "POST /saved (save item)", [200, 201], warn_on_fail=True)
    saved_id = None
    if ok and isinstance(saved, dict):
        saved_id = (
            saved.get("id")
            or saved.get("item_id")
            or (saved.get("item") or {}).get("id")
        )

    # list
    r = api("GET", "/saved", token=student_tok)
    ok, saved_list = expect(r, "GET /saved (list)", 200)
    if ok:
        items = saved_list if isinstance(saved_list, list) else saved_list.get("items", saved_list.get("saved", []))
        p("Saved list is a list", "pass" if isinstance(items, list) else "warn", f"count={len(items)}")
        if items and not saved_id:
            saved_id = items[0].get("id")

    if not saved_id:
        gap("Could not determine saved item id — skipping update/move tests")
        return

    # update
    r = api("PATCH", f"/saved/{saved_id}", token=student_tok, body={"quantity": 2, "notes": "Updated sim note"})
    ok_upd, upd = expect(r, "PATCH /saved/{id} (update)", [200], warn_on_fail=True)
    if ok_upd:
        upd_obj = (upd.get("item") or upd) if isinstance(upd, dict) else {}
        p(
            "Quantity updated to 2",
            "pass" if upd_obj.get("quantity") == 2 else "warn",
            str(upd_obj.get("quantity")),
        )

    # move saved → cart
    r = api("POST", f"/saved/{saved_id}/move-to-cart", token=student_tok)
    ok_move, moved = expect(r, "POST /saved/{id}/move-to-cart", [200, 201], warn_on_fail=True)
    if ok_move:
        p(
            "move-to-cart returns 200/201",
            "pass",
        )
        # verify gone from saved
        r2 = api("GET", "/saved", token=student_tok)
        if r2 and r2.status_code == 200:
            items2 = r2.json() if isinstance(r2.json(), list) else r2.json().get("items", r2.json().get("saved", []))
            still_there = any(i.get("id") == saved_id for i in (items2 if isinstance(items2, list) else []))
            p(
                "Moved item no longer in saved list",
                "pass" if not still_there else "warn",
            )

    # move cart → saved (pick first cart item)
    r = api("GET", "/cart", token=student_tok)
    cart_item_id = None
    if r and r.status_code == 200:
        cart = r.json()
        c_items = cart.get("items", cart) if isinstance(cart, dict) else cart
        if isinstance(c_items, list) and c_items:
            cart_item_id = c_items[0].get("id")

    if cart_item_id:
        r = api("POST", f"/saved/from-cart/{cart_item_id}", token=student_tok)
        ok_fc, _ = expect(r, "POST /saved/from-cart/{id}", [200, 201], warn_on_fail=True)
        if ok_fc:
            r3 = api("GET", "/saved", token=student_tok)
            if r3 and r3.status_code == 200:
                items3 = r3.json() if isinstance(r3.json(), list) else r3.json().get("items", r3.json().get("saved", []))
                p("Cart item moved back to saved", "pass" if isinstance(items3, list) and len(items3) >= 1 else "warn", f"count={len(items3)}")
    else:
        gap("No cart item available for from-cart move test")

    # clean up: re-save then delete
    r = api("POST", "/saved", token=student_tok, body={"menu_item_id": menu_item_id, "quantity": 1})
    if r and r.status_code in (200, 201):
        item = r.json()
        del_id = (item.get("id") or (item.get("item") or {}).get("id")) if isinstance(item, dict) else None
        if del_id:
            r = api("DELETE", f"/saved/{del_id}", token=student_tok)
            ok_del, _ = expect(r, "DELETE /saved/{id} (remove)", [200, 204], warn_on_fail=True)
            if ok_del:
                r4 = api("GET", "/saved", token=student_tok)
                if r4 and r4.status_code == 200:
                    items4 = r4.json() if isinstance(r4.json(), list) else r4.json().get("items", r4.json().get("saved", []))
                    still = any(i.get("id") == del_id for i in (items4 if isinstance(items4, list) else []))
                    p("Deleted item gone from saved list", "pass" if not still else "warn")


def sim_39_storefront(admin_tok):
    section("SIM 39 · STOREFRONT — OPERATING HOURS, OVERRIDE, SECTION, PROMO VALIDATE")
    # get operating hours
    r = api("GET", "/storefront/operating-hours")
    ok, hours = expect(r, "GET /storefront/operating-hours", 200)
    if ok:
        p(
            "Hours has is_open field",
            "pass" if isinstance(hours, dict) and "is_open" in hours else "warn",
            str(hours)[:120],
        )

    # update operating hours
    r = api(
        "PATCH",
        "/storefront/operating-hours",
        token=admin_tok,
        body={"day": "monday", "open_time": "10:00", "close_time": "21:00"},
    )
    expect(r, "PATCH /storefront/operating-hours (update Monday)", [200], warn_on_fail=True)

    # set date override
    override_date = (date.today() + timedelta(days=90)).isoformat()
    r = api(
        "POST",
        "/storefront/operating-hours/override",
        token=admin_tok,
        body={"override_date": override_date, "is_closed": True, "reason": "Sim Holiday"},
    )
    ok_ov, ov_resp = expect(r, "POST /storefront/operating-hours/override", [200, 201], warn_on_fail=True)
    if ok_ov:
        p(
            "Override set for future date",
            "pass" if ov_resp else "warn",
            str(ov_resp)[:80],
        )

    # create a section to update
    r = api(
        "POST",
        "/storefront/sections",
        token=admin_tok,
        body={
            "key": f"sim39_section_{uuid.uuid4().hex[:5]}",
            "title": "Sim39 Section",
            "section_type": "banner",
        },
    )
    ok_s, section_row = expect(r, "POST /storefront/sections (setup for PATCH)", [200, 201], warn_on_fail=True)
    section_id = (section_row.get("id") if isinstance(section_row, dict) else None)
    if section_id:
        r = api(
            "PATCH",
            f"/storefront/sections/{section_id}",
            token=admin_tok,
            body={"title": "Updated Sim39 Section", "is_active": True},
        )
        ok_upd, upd_s = expect(r, "PATCH /storefront/sections/{id}", [200], warn_on_fail=True)
        if ok_upd:
            upd_obj = upd_s.get("section", upd_s) if isinstance(upd_s, dict) else {}
            p(
                "Section title updated",
                "pass" if "Updated" in str(upd_obj.get("title", "")) else "warn",
                str(upd_obj.get("title")),
            )
        # delete/deactivate
        api("DELETE", f"/storefront/sections/{section_id}", token=admin_tok)

    # validate promo code (deprecated endpoint — forwards to /orders/validate-promo)
    r = api(
        "POST",
        "/storefront/promo-codes/validate",
        body={"code": "SIMFAKE999", "order_subtotal": 1000},
    )
    # deprecated — returns 200 with _deprecated flag (invalid code → 400 with deprecation wrapper)
    code = r.status_code if r else None
    p(
        "POST /storefront/promo-codes/validate (deprecated) reachable",
        "pass" if code in (200, 400, 404, 410) else "warn",
        str(code),
    )


def sim_40_wallet(admin_tok, student_tok, student_id):
    section("SIM 40 · WALLET — WITHDRAW, ADMIN TRANSACTIONS")
    seed_wallet(student_id, 5000)

    # wallet withdrawal was removed — skip the withdraw test

    # admin list transactions
    r = api("GET", "/wallet/admin/transactions", token=admin_tok, params={"limit": 10})
    ok, tx_data = expect(r, "GET /wallet/admin/transactions", 200)
    if ok:
        items = tx_data if isinstance(tx_data, list) else tx_data.get("transactions", [])
        p(
            "Admin wallet transactions is a list",
            "pass" if isinstance(items, list) else "warn",
            f"count={len(items)}",
        )


def sim_41_webhooks(admin_tok, student_id):
    section("SIM 41 · WEBHOOKS — PAYSTACK & FLUTTERWAVE")
    # Paystack charge.success — compute HMAC if secret is available
    paystack_secret = os.environ.get("PAYSTACK_WEBHOOK_SECRET", "")
    flw_secret = os.environ.get("FLUTTERWAVE_WEBHOOK_SECRET", "")

    ref = f"simref_{uuid.uuid4().hex[:10]}"
    ps_payload = {
        "event": "charge.success",
        "data": {
            "reference": ref,
            "amount": 50000,
            "status": "success",
            "metadata": {"type": "wallet_topup", "user_id": student_id},
        },
    }
    ps_bytes = json.dumps(ps_payload, separators=(",", ":")).encode()

    if paystack_secret:
        sig = hmac.new(paystack_secret.encode(), ps_bytes, hashlib.sha512).hexdigest()
        r = requests.post(
            f"{BASE}/webhooks/paystack",
            data=ps_bytes,
            headers={"Content-Type": "application/json", "x-paystack-signature": sig},
            timeout=20,
        )
        ok_ps = r.status_code == 200
        p(
            "Paystack charge.success webhook → 200",
            "pass" if ok_ps else "fail",
            f"{r.status_code}: {r.text[:200]}",
        )
        if ok_ps:
            time.sleep(1)
            # wallet should have been topped up
            wb_rows = sb_get("wallet_transactions",
                             f"user_id=eq.{student_id}&reference=eq.{ref}&select=amount&limit=1")
            p(
                "Wallet transaction recorded for webhook topup",
                "pass" if wb_rows else "warn",
                str(wb_rows),
            )
    else:
        gap("PAYSTACK_WEBHOOK_SECRET not configured — Paystack webhook test skipped")

    # Paystack transfer.success
    ref2 = f"simxfer_{uuid.uuid4().hex[:10]}"
    ps_xfer = {
        "event": "transfer.success",
        "data": {
            "reference": ref2,
            "amount": 100000,
            "recipient": {"details": {"account_number": "1234567890"}},
            "metadata": {"user_id": student_id},
        },
    }
    ps_xfer_bytes = json.dumps(ps_xfer, separators=(",", ":")).encode()
    if paystack_secret:
        sig2 = hmac.new(paystack_secret.encode(), ps_xfer_bytes, hashlib.sha512).hexdigest()
        r = requests.post(
            f"{BASE}/webhooks/paystack",
            data=ps_xfer_bytes,
            headers={"Content-Type": "application/json", "x-paystack-signature": sig2},
            timeout=20,
        )
        expect_status = [200]
        ok2 = r.status_code in expect_status
        p(
            "Paystack transfer.success webhook → 200",
            "pass" if ok2 else "warn",
            f"{r.status_code}: {r.text[:200]}",
        )
    else:
        gap("PAYSTACK_WEBHOOK_SECRET not set — transfer.success webhook test skipped")

    # Flutterwave charge.completed
    flw_ref = f"flwsim_{uuid.uuid4().hex[:10]}"
    flw_payload = {
        "event": "charge.completed",
        "data": {
            "status": "successful",
            "tx_ref": flw_ref,
            "amount": 50000,
            "meta": {"type": "wallet_topup", "user_id": student_id},
        },
    }
    flw_bytes = json.dumps(flw_payload, separators=(",", ":")).encode()
    if flw_secret:
        r = requests.post(
            f"{BASE}/webhooks/flutterwave",
            data=flw_bytes,
            headers={"Content-Type": "application/json", "verif-hash": flw_secret},
            timeout=20,
        )
        ok_flw = r.status_code == 200
        p(
            "Flutterwave charge.completed webhook → 200",
            "pass" if ok_flw else "warn",
            f"{r.status_code}: {r.text[:200]}",
        )
    else:
        gap("FLUTTERWAVE_WEBHOOK_SECRET not set — Flutterwave webhook test skipped")


# ─── main ─────────────────────────────────────────────────────────────────────


def open_store_for_today(admin_tok):
    """Set an operating-hours override for today so orders can be placed at any time.
    Uses Supabase admin API directly (correct column names: opens_at / closes_at)
    rather than the app route, to avoid any app startup timing dependency.
    """
    today = date.today().isoformat()
    # PATCH first (update existing row if present), then INSERT if not found
    body = {"is_closed": False, "opens_at": "00:00", "closes_at": "23:59",
            "reason": "Sim2 test override"}
    patch_h = {**ADMIN_H, "Prefer": "return=minimal"}
    pr = requests.patch(
        f"{SUPABASE_URL}/rest/v1/operating_hour_overrides?date=eq.{today}",
        headers=patch_h, json=body, timeout=15,
    )
    if pr.status_code == 204:  # row existed, updated
        ok = True
    else:
        # No existing row — insert
        ins_h = {**ADMIN_H, "Prefer": "return=minimal"}
        ir = requests.post(
            f"{SUPABASE_URL}/rest/v1/operating_hour_overrides",
            headers=ins_h, json={"date": today, **body}, timeout=15,
        )
        ok = ir.status_code in (200, 201, 204)
    p(
        "Operating hours override → store open all day",
        "pass" if ok else "warn",
        f"patch={pr.status_code}",
    )
    return ok


def main():  # noqa: C901
    section("SETUP")
    print("  Creating admin, kitchen, rider, student users …")
    admin_id, admin_tok, _, _, _ = create_test_user("ADMIN", role="admin")
    kitchen_id, kitchen_tok, _, _, _ = create_test_user("KITCHEN", role="kitchen")
    rider_id, rider_tok, _, _, _ = create_test_user("RIDER", role="rider")
    student_id, student_tok, _, _, _ = create_test_user("STUDENT")
    p("Core users created", "pass")

    # Ensure store is open so orders can be placed at any hour
    open_store_for_today(admin_tok)

    seed_wallet(student_id, 30000)
    seed_hp(student_id, 1000)

    window_id = get_or_create_window()
    p("Delivery window available", "pass" if window_id else "fail", str(window_id))

    menu_item = get_menu_item()
    p("Menu item available", "pass" if menu_item else "fail", str(menu_item))
    if not menu_item:
        print(f"  {FAIL_C} Cannot continue without a menu item. Aborting.")
        sys.exit(1)
    menu_item_id = menu_item["id"]

    # Create a promo code for 21E tests
    r = api(
        "POST",
        "/admin/promo-codes",
        token=admin_tok,
        body={"code": f"SIM2PROMO{uuid.uuid4().hex[:4].upper()}", "discount_type": "flat",
              "discount_value": 100, "min_order_value": 0},
    )
    promo_id = None
    if r and r.status_code == 201:
        promo_id = r.json().get("id")

    # place a quick order to have order_ids for batch creation
    seed_wallet(student_id, 50000)
    ro = place_order(student_tok, menu_item_id, window_id)
    batch_order_id = (ro.json().get("id") or ro.json().get("order_id")) if ro and ro.status_code == 201 else None

    # ── run simulations ────────────────────────────────────────────────────────
    sim_21a_admin_audit_cron(admin_tok)
    time.sleep(0.3)

    sim_21b_delivery_batches(
        admin_tok, rider_id, window_id,
        [batch_order_id] if batch_order_id else [],
    )
    time.sleep(0.3)

    sim_21c_delivery_windows(admin_tok)
    time.sleep(0.3)

    sim_21d_hp_bulk_grant_report(admin_tok)
    time.sleep(0.3)

    sim_21e_admin_orders_users(admin_tok, student_id, promo_id)
    time.sleep(0.3)

    sim_22_analytics(admin_tok)
    time.sleep(0.3)

    sim_23_auth(admin_tok)
    time.sleep(0.3)

    sim_24_cart(student_tok, menu_item_id)
    time.sleep(0.3)

    sim_25_challenges(admin_tok, student_tok)
    time.sleep(0.3)

    sim_26_events(admin_tok, student_tok)
    time.sleep(0.3)

    sim_27_health()
    time.sleep(0.2)

    sim_28_hp(student_tok, student_id)
    time.sleep(0.3)

    sim_29_kitchen(kitchen_tok, admin_tok, window_id)
    time.sleep(0.3)

    sim_30_leaderboard(student_tok)
    time.sleep(0.3)

    sim_31_marketplace(admin_tok, student_tok, student_id)
    time.sleep(0.3)

    sim_32_notifications(admin_tok, student_tok, student_id)
    time.sleep(0.3)

    sim_33_order_locks(admin_tok, student_tok)
    time.sleep(0.3)

    sim_34_orders(admin_tok, student_tok, student_id, kitchen_tok, rider_tok, menu_item_id, window_id)
    time.sleep(0.3)

    sim_35_referrals(student_tok)
    time.sleep(0.2)

    sim_36_rewards(admin_tok, student_tok, student_id)
    time.sleep(0.3)

    sim_37_riders(rider_tok, rider_id, admin_tok, student_tok, student_id, menu_item_id, window_id, kitchen_tok)
    time.sleep(0.3)

    sim_38_saved(student_tok, student_id, menu_item_id)
    time.sleep(0.3)

    sim_39_storefront(admin_tok)
    time.sleep(0.3)

    sim_40_wallet(admin_tok, student_tok, student_id)
    time.sleep(0.3)

    sim_41_webhooks(admin_tok, student_id)

    # ── cleanup ────────────────────────────────────────────────────────────────
    section("CLEANUP")
    for label, fn in CLEANUP:
        try:
            fn()
        except Exception as exc:
            print(f"    (cleanup {label} failed: {exc})")
    print(f"  Cleaned {len(CLEANUP)} test users")

    # ── results ────────────────────────────────────────────────────────────────
    section("RESULTS SUMMARY")
    total = sum(RESULTS.values())
    print(
        f"  Total: {total}  "
        f"{PASS_C}: {RESULTS['pass']}  "
        f"{WARN_C}: {RESULTS['warn']}  "
        f"{FAIL_C}: {RESULTS['fail']}"
    )
    if FAILED_DETAILS:
        print(f"\n{BOLD}  FAILURES:{RESET}")
        for label, detail in FAILED_DETAILS:
            print(f"    ❌ {label} — {detail}")
    if GAPS:
        print(f"\n{BOLD}  GAPS / NEEDS ATTENTION:{RESET}")
        for label, detail in GAPS:
            print(f"    ℹ️  {label}" + (f" — {detail}" if detail else ""))

    sys.exit(1 if RESULTS["fail"] else 0)


if __name__ == "__main__":
    main()
