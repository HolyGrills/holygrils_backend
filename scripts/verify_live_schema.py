#!/usr/bin/env python3
"""Read-only verification of the application contract against live Supabase.

The PostgREST root endpoint exposes the live OpenAPI document.  That document
is the reliable source of column metadata even when a table is empty, so the
verifier does not need to insert probe rows into the production database.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Iterable

import requests


BASE = os.environ["SUPABASE_URL"].rstrip("/")
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
}
TIMEOUT = int(os.environ.get("LIVE_SCHEMA_TIMEOUT", "20"))

REQUIRED_COLUMNS: dict[str, set[str]] = {
    "profiles": {"id", "email", "role", "is_active", "hp_balance", "wallet_balance"},
    "wallets": {"user_id", "balance"},
    "daily_checkins": {"id", "user_id", "checkin_date"},
    "events": {"id", "title", "starts_at", "is_published"},
    "event_ticket_tiers": {
        "id", "event_id", "name", "price_naira", "price_hp", "capacity", "sold_count",
    },
    "event_tickets": {"id", "event_id", "user_id", "tier_id"},
    "feature_flags": {"feature_name", "is_active"},
    "menu_items": {"id", "category_id", "name", "price", "hp_earn_value"},
    "system_settings": {"key", "value"},
}


def fetch_columns(table: str) -> tuple[set[str] | None, str | None]:
    """Read a table's columns from PostgREST's live OpenAPI schema."""
    response = requests.get(
        f"{BASE}/rest/v1/",
        headers={**HEADERS, "Accept": "application/openapi+json"},
        timeout=TIMEOUT,
    )
    if response.status_code >= 400:
        return None, f"OpenAPI HTTP {response.status_code}: {response.text[:160]}"
    try:
        definition = response.json().get("definitions", {}).get(table)
        properties = (definition or {}).get("properties", {})
    except (TypeError, ValueError):
        properties = {}
    if properties:
        return set(properties), None

    # Keep a useful diagnostic if a table is not present in the schema cache.
    response = requests.get(
        f"{BASE}/rest/v1/{table}",
        headers=HEADERS,
        params={"select": "*", "limit": "1"},
        timeout=TIMEOUT,
    )
    if response.status_code == 404:
        return None, "table not exposed by PostgREST"
    if response.status_code >= 400:
        return None, f"HTTP {response.status_code}: {response.text[:160]}"
    body = response.json()
    if not body:
        return None, "table is empty and missing from the live OpenAPI schema"
    return set(body[0]), None


def main() -> int:
    report: list[dict] = []
    failures = 0
    for table, required in REQUIRED_COLUMNS.items():
        try:
            columns, note = fetch_columns(table)
        except Exception as exc:
            columns, note = None, f"{type(exc).__name__}: {exc}"
        missing = sorted(required - columns) if columns is not None else []
        status = "PASS" if columns is not None and not missing else "DRIFT"
        if status != "PASS":
            failures += 1
        report.append({
            "table": table,
            "status": status,
            "missing_columns": missing,
            "note": note,
        })

    print(json.dumps({"status": "PASS" if failures == 0 else "DRIFT", "tables": report}, indent=2))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())