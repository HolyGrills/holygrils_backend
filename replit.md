# Holy Grills Backend API

## Project Overview

**Holy Grills** is a student-focused food ordering and loyalty-points (HP — Holy Points) platform built for FUTA. This is the Flask REST API backend.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | Flask 3.x |
| Database | Supabase (PostgreSQL via REST API) |
| Auth | Supabase Auth + custom JWT middleware |
| Payments | Paystack (card + virtual accounts) |
| Email | Resend (transactional email) |
| Push Notifications | OneSignal |
| Background Jobs | Celery + Redis |
| API Docs | Flasgger (Swagger UI at `/api/docs/`) |

## How to Run

```bash
python run.py
```

The app starts on port 5000. Swagger UI available at `/api/docs/`.

## Key Files

| File | Purpose |
|------|---------|
| `run.py` | Entry point |
| `app/__init__.py` | App factory — all blueprints registered here |
| `app/config.py` | All config from environment variables |
| `app/db.py` | Supabase REST client |
| `app/messages.py` | All user-facing copy (edit here for text changes) |
| `FRONTEND_INTEGRATION.md` | Complete API guide — every endpoint, all user flows |
| `ENV_CONFIGURATION.md` | Full environment variable reference |
| `migrations/run10_new_features.sql` | Latest DB schema migration (Phase 3) |
| `migrations/20260808_remove_badges_daily_spin_and_paid_exclusive.sql` | Disable removed badge/challenge and paid-spin features |

## Running Tests

```bash
# Unit tests (fast, no live server required)
python -m pytest tests/ -v

# Full integration test suite (requires running server + live Supabase)
python test_all.py

# Phase 3 feature tests
python -m pytest tests/test_phase3_features.py -v
```

## Required Secrets (Replit Secrets panel)

| Secret | Description |
|--------|-------------|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-side DB access key |
| `SUPABASE_ANON_KEY` | Public anon key |
| `JWT_SECRET` | JWT signing secret (= Supabase JWT secret) |
| `SECRET_KEY` | Flask session secret |
| `RESEND_API_KEY` | Resend transactional email API key |
| `REDIS_URL` | Redis connection URL (for Celery) |
| `CELERY_BROKER_URL` | Celery broker (defaults to REDIS_URL) |
| `CELERY_RESULT_BACKEND` | Celery result backend (defaults to REDIS_URL) |

## Optional Secrets

| Secret | Default | Description |
|--------|---------|-------------|
| `WELCOME_BONUS_HP` | 50 | HP on first delivered order |
| `BIRTHDAY_HP` | 150 | HP on birthday |
| `REFERRAL_HP` | 75 | HP per completed referral |
| `REVIEW_HP` | 20 | HP for leaving a review |
| `EVENT_CHECKIN_HP` | 40 | HP for event check-in |
| `WALLET_TOPUP_HP` | 50 | HP for wallet top-up ≥ ₦3000 |
| `SOCIAL_SHARE_HP` | 25 | HP for social share |
| `SIGNUP_BONUS_HP` | 0 | HP on account creation |

## User Preferences

- Keep existing project structure and naming conventions
- All user-facing strings go in `app/messages.py` — never hardcode copy in routes
- All business logic goes in `app/services/` — routes should be thin
- Use `get_logger(__name__)` from `app.utils.logger` for all logging
- Use `with_retry` from `app.utils.retry` for all external API calls
- Feature flags in `feature_flags` DB table control every major feature — no hardcoded on/off switches
- Email uses Resend (not OneSignal) — OneSignal is push-only
- Badges, milestones, and challenge rewards are retired; do not reintroduce their routes or award services
- Exclusive spins are leaderboard-winner rewards only; they cannot be purchased with HP
- Menu HP multiplier supports only 1x (off) or 2x (active)
