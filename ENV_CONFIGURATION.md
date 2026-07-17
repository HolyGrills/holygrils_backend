# Holy Grills — Environment Configuration Reference

Every environment variable the app reads, what it controls, its default, and
**where to set it**. There are two places to configure values:

| Where | What lives there |
|-------|-----------------|
| **Replit Secrets** (or `.env` for local) | Any value that is secret or deployment-specific — keys, tokens, URLs, passwords |
| **`app/messages.py`** | User-facing strings — notification titles, bodies, email subjects, error messages |

> **Rule of thumb:** If it's a credential, URL, or numeric tuning knob → Secrets/`.env`.
> If it's the wording of a message a user reads → `app/messages.py`.

---

## 1 · Replit Secrets / `.env` Variables

### 1.1 App Identity

| Variable | Description | Default (if not set) |
|----------|-------------|----------------------|
| `SECRET_KEY` | Flask session secret (random string) | *(required)* |
| `APP_NAME` | Platform name used in emails and push notifications | `Holy Grills` |
| `APP_TAGLINE` | Sign-off line on all emails | `Holy Grills FUTA` |
| `FLASK_DEBUG` | Enable debug mode (`true`/`false`) | `false` |
| `FRONTEND_URL` | Allowed CORS origin for the mobile/web frontend | `http://localhost:3000` |
| `CORS_ORIGINS` | Comma-separated list of allowed origins | `*` |
| `SWAGGER_CONTACT_EMAIL` | Contact email shown in API docs | `dev@example.com` |

### 1.2 Supabase (Database + Auth)

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPABASE_URL` | Your project URL (`https://xxx.supabase.co`) | *(required — app crashes without it)* |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key for server-side DB access | *(required)* |
| `SUPABASE_ANON_KEY` | Anon/public key | *(required)* |
| `JWT_SECRET` | JWT signing secret — set to Supabase → Settings → API → JWT Secret | Falls back to `SUPABASE_JWT_SECRET`, then `SECRET_KEY` |
| `SUPABASE_JWT_SECRET` | Alternative name for JWT secret | *(see above)* |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRES` | Access token TTL (seconds) | `3600` |
| `JWT_REFRESH_TOKEN_EXPIRES` | Refresh token TTL (seconds) | `2592000` |
| `JWT_REFRESH_WINDOW_MINUTES` | Rotate token when N minutes remain | `5` |

### 1.3 Payments — Paystack

| Variable | Description | Default |
|----------|-------------|---------|
| `PAYSTACK_SECRET_KEY` | Secret key (`sk_live_…`) | *(empty — payments disabled)* |
| `PAYSTACK_PUBLIC_KEY` | Public key (`pk_live_…`) | *(empty)* |
| `PAYSTACK_WEBHOOK_SECRET` | Webhook signing secret | *(empty)* |
| `PAYSTACK_PREFERRED_BANK` | Bank for virtual account provisioning | `wema-bank` |
| `PAYSTACK_SANDBOX_MOCK_NUBAN` | `true` to skip real NUBAN provisioning in dev | `false` |

### 1.4 Payments — Flutterwave (optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `FLUTTERWAVE_SECRET_KEY` | Secret key (`FLWSECK_LIVE-…`) | *(empty)* |
| `FLUTTERWAVE_WEBHOOK_SECRET` | Webhook signing secret | *(empty)* |

### 1.5 Notifications — OneSignal

| Variable | Description | Default |
|----------|-------------|---------|
| `ONESIGNAL_APP_ID` | OneSignal app UUID | *(empty — notifications skipped)* |
| `ONESIGNAL_API_KEY` | OneSignal REST API key (`os_v2_…`) | *(empty)* |
| `ONESIGNAL_BASE_URL` | Override base URL for testing | `https://api.onesignal.com` |
| `EMAIL_FROM` | Sender email address | `noreply@holygrills.ng` |
| `EMAIL_FROM_NAME` | Sender display name on emails | `Holy Grills` |

### 1.6 Redis / Celery (background jobs)

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `CELERY_BROKER_URL` | Celery broker (falls back to `REDIS_URL`) | same as `REDIS_URL` |
| `CELERY_RESULT_BACKEND` | Celery result backend | same as `REDIS_URL` |

### 1.7 HP (Holy Points) Economy — Award Amounts

| Variable | Description | Default |
|----------|-------------|---------|
| `SIGNUP_BONUS_HP` | HP granted on account creation | `0` (disabled) |
| `WELCOME_BONUS_HP` | HP for first delivered order | `50` |
| `REVIEW_HP` | HP for leaving an order review | `20` |
| `REFERRAL_HP` | HP awarded per completed referral | `75` |
| `EVENT_CHECKIN_HP` | HP for event check-in | `40` |
| `BIRTHDAY_HP` | HP awarded on user's birthday | `150` |
| `WALLET_TOPUP_HP` | HP for wallet top-up | `50` |
| `WALLET_TOPUP_MIN` | Minimum top-up amount (₦) to earn HP | `3000` |
| `SUBSCRIPTION_HP` | HP for storefront subscription | `50` |
| `SOCIAL_SHARE_HP` | HP for social media sharing | `25` |
| `MARKETPLACE_PURCHASE_HP` | HP for marketplace purchase | `50` |
| `GRADUATION_HP` | One-time HP for graduation claim | `1000` |
| `LOGIN_STREAK_HP` | HP per daily login streak check-in | `2` |
| `SHARE_PROMPT_HP` | HP for sharing an order | `25` |

### 1.8 HP Economy — Rates & Decay

| Variable | Description | Default |
|----------|-------------|---------|
| `HP_PER_NAIRA_FOOD` | HP earned per ₦1 food spend | `0.1` |
| `HP_LIABILITY_VALUE` | ₦ value of 1 HP (accounting) | `0.185` |
| `HP_UNLOCK_RATE_PCT` | % of food spend that unlocks pending HP | `0.30` |
| `HP_CURRENCY_NAME` | Display name for HP currency in messages | `HP` |
| `HP_DECAY_ONSET_DAYS` | Days of inactivity before HP decay starts | `120` |
| `HP_DECAY_RATE_MONTHLY` | Monthly decay rate (fraction) | `0.10` |
| `MONTHLY_HP_CAP` | Max HP per month from free activities | `800` |

### 1.9 Tier System

| Variable | Description | Default |
|----------|-------------|---------|
| `TIER_GRACE_PERIOD_DAYS` | Days before tier downgrade after falling below threshold | `7` |
| `TIER_MULTIPLIERS` | JSON map of tier-slug → HP earn multiplier | See config.py |
| `TIER_THRESHOLDS` | JSON map of tier-slug → rolling-120-day HP threshold | See config.py |

### 1.10 Referral Milestones

| Variable | Description | Default |
|----------|-------------|---------|
| `REFERRAL_MILESTONE_1_COUNT` | Referral count for first milestone | `5` |
| `REFERRAL_MILESTONE_2_COUNT` | Referral count for second milestone | `10` |
| `REFERRAL_MILESTONE_5_HP` | Bonus HP at 5-referral milestone | `150` |
| `REFERRAL_MILESTONE_10_HP` | Bonus HP at 10-referral milestone | `400` |
| `REFERRAL_MILESTONE_REPEAT_HP` | HP for every repeat milestone | `1500` |
| `REFERRAL_MILESTONE_REPEAT_BASE` | Referral count where repeats begin | `50` |
| `REFERRAL_MILESTONE_REPEAT_INTERVAL` | Interval between repeat milestones | `25` |

### 1.11 Flash Sales

| Variable | Description | Default |
|----------|-------------|---------|
| `FLASH_DISCOUNT_PCT` | Discount fraction on flash deals | `0.50` |
| `FLASH_MAX_QTY` | Max redemptions per flash window | `5` |

### 1.12 Squad Orders

| Variable | Description | Default |
|----------|-------------|---------|
| `SQUAD_ORDER_ENABLED` | Enable squad order feature | `true` |
| `SQUAD_ORDER_MIN_ITEMS` | Min item quantity to qualify as squad order | `3` |
| `SQUAD_ORDER_MAX_ITEMS` | Max item quantity allowed | `20` |
| `SQUAD_DELIVERY_DISCOUNT_ENABLED` | Waive delivery fee for squad orders | `true` |
| `SQUAD_DELIVERY_DISCOUNT_PCT` | % of delivery fee waived | `100` |
| `SQUAD_ORDER_DISCOUNT_ENABLED` | Apply % off subtotal | `false` |
| `SQUAD_ORDER_DISCOUNT_PCT` | Subtotal discount % | `10` |
| `SQUAD_HP_SPLIT_ENABLED` | Split HP across squad members | `true` |
| `SQUAD_REFERRAL_WINDOW_DAYS` | Days after being added to squad for referral attribution | `7` |

### 1.13 Wallet

| Variable | Description | Default |
|----------|-------------|---------|
| `WALLET_MIN_CARD_TOPUP` | Minimum card top-up amount (₦) | `100` |
| `WALLET_MIN_WITHDRAWAL` | Minimum withdrawal amount (₦) | `500` |
| `WALLET_REF_PREFIX` | Transaction reference prefix | `HG-WALLET-` |

### 1.14 Order Locks

| Variable | Description | Default |
|----------|-------------|---------|
| `ORDER_LOCK_MAX_RESCHEDULES` | Max reschedules per lock | `1` |
| `ORDER_LOCK_MAX_DISCOUNT_PCT` | Max discount % admin can assign | `50` |
| `ORDER_LOCK_DEFAULT_DISCOUNT_PCT` | Default discount % | `10` |

### 1.15 Login Streak

| Variable | Description | Default |
|----------|-------------|---------|
| `LOGIN_STREAK_WEEK1_HP` | HP bonus for completing week 1 | `25` |
| `LOGIN_STREAK_WEEK2_HP` | HP bonus for completing week 2 | `40` |
| `LOGIN_STREAK_WEEK3_HP` | HP bonus for completing week 3 | `60` |
| `LOGIN_STREAK_WEEK4_HP` | HP bonus for completing week 4 | `80` |
| `STREAK_MAX_MISSED_DAYS` | Missed days allowed per 7-day cycle | `2` |
| `STREAK_RECLAIM_MIN_TOPUP` | Min ₦ wallet top-up to reclaim missed day | `1000` |

### 1.16 Win-Back Notifications

| Variable | Description | Default |
|----------|-------------|---------|
| `WINBACK_DAY1` | Days of inactivity for first win-back nudge | `70` |
| `WINBACK_DAY2` | Days for second nudge | `95` |
| `WINBACK_DAY3` | Days for final nudge (before decay warning) | `118` |

### 1.17 Notification Throttling

| Variable | Description | Default |
|----------|-------------|---------|
| `NOTIFICATION_GAP_MINUTES` | Min minutes between same-type notifications per user | `30` |
| `NOTIFICATION_DAILY_CAP` | Max non-critical notifications per user per day | `20` |

> These can also be overridden per-admin in the `system_settings` DB table without a deploy.

### 1.18 Marketplace & Cart

| Variable | Description | Default |
|----------|-------------|---------|
| `LOW_CODE_INVENTORY_THRESHOLD` | Trigger low-inventory alert at this many codes | `5` |
| `ABANDONED_CART_MINUTES` | Minutes before cart is considered abandoned | `60` |
| `MARKETPLACE_DEFAULT_VENDOR_NAME` | Default vendor name for unlisted vendors | `APP_NAME` |

### 1.19 HP Bundles & Spin Wheel

| Variable | Description | Default |
|----------|-------------|---------|
| `HP_BUNDLE_PRICE_PER_HP` | ₦ per HP when purchasing a bundle | `5.0` |
| `HP_BUNDLE_MIN_PURCHASE` | Minimum bundle size (HP) | `100` |
| `HP_BUNDLES` | JSON array of `{hp, label}` bundle tiers | See config.py |
| `SPIN_COST_HP` | HP cost per extra spin | `10` |
| `SPIN_PRIZES` | JSON array of `{label, hp, weight}` prize table | See config.py |

### 1.20 Ordering Window

| Variable | Description | Default |
|----------|-------------|---------|
| `ORDERING_WINDOW_OPEN_TIME` | When orders can start being placed | `08:00` |
| `ORDERING_WINDOW_CLOSE_TIME` | When ordering closes | `16:00` |
| `CALLBACK_WINDOW_MINUTES` | Minutes of grace after window closes | `30` |

### 1.21 HP Transfer

| Variable | Description | Default |
|----------|-------------|---------|
| `HP_TRANSFER_MIN_AMOUNT` | Minimum HP per transfer | `10` |
| `HP_TRANSFER_MIN_ORDERS` | Minimum completed orders before transfer is allowed | `3` |

### 1.22 Registration & Validation

| Variable | Description | Default |
|----------|-------------|---------|
| `MINIMUM_AGE` | Minimum registration age | `16` |
| `PHONE_REGEX_PATTERN` | Regex for Nigerian phone numbers | `^(\+234\|0)[789]\d{9}$` |

### 1.23 First-Order Gift

| Variable | Description | Default |
|----------|-------------|---------|
| `FIRST_ORDER_GIFT_ENABLED` | Toggle first-order hot dog gift | `true` |

### 1.24 Leaderboard

| Variable | Description | Default |
|----------|-------------|---------|
| `LEADERBOARD_DEFAULT_LIMIT` | Default page size | `10` |
| `LEADERBOARD_MAX_LIMIT` | Maximum page size | `50` |

### 1.25 Rewards

| Variable | Description | Default |
|----------|-------------|---------|
| `REWARD_FULFILMENT_HOURS` | Hours quoted in reward fulfilment confirmation email | `24` |

### 1.26 Rate Limits (per IP)

| Variable | Description | Default |
|----------|-------------|---------|
| `RATE_LIMIT_REGISTER_REQUESTS` | Max registrations per window | `10` |
| `RATE_LIMIT_REGISTER_WINDOW` | Window (seconds) | `3600` |
| `RATE_LIMIT_LOGIN_REQUESTS` | Max login attempts per window | `20` |
| `RATE_LIMIT_LOGIN_WINDOW` | Window (seconds) | `900` |
| `RATE_LIMIT_ORDERS_REQUESTS` | Max order placements per window | `10` |
| `RATE_LIMIT_ORDERS_WINDOW` | Window (seconds) | `300` |
| `RATE_LIMIT_RESET_PW_REQUESTS` | Max password reset requests | `5` |
| `RATE_LIMIT_RESET_PW_WINDOW` | Window (seconds) | `3600` |
| `RATE_LIMIT_REFRESH_REQUESTS` | Max token refresh calls per window | `30` |
| `RATE_LIMIT_REFRESH_WINDOW` | Window (seconds) | `60` |
| `RATE_LIMIT_VERIFY_EMAIL_REQUESTS` | Max resend verification emails | `3` |
| `RATE_LIMIT_VERIFY_EMAIL_WINDOW` | Window (seconds) | `3600` |
| `RATE_LIMIT_DEVICE_TOKEN_REQUESTS` | Max device token registrations per window | `20` |
| `RATE_LIMIT_DEVICE_TOKEN_WINDOW` | Window (seconds) | `3600` |

### 1.27 Misc

| Variable | Description | Default |
|----------|-------------|---------|
| `MAX_CONTENT_LENGTH_MB` | Maximum request body size (MB) | `10` |

---

## 2 · Where to Set Secrets vs Edit in Code

### Replit Secrets (Replit → Secrets panel, or `.env` file locally)

Set the following here — **never put these in source code**:

```
# Required for app to start
SECRET_KEY
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_ANON_KEY
JWT_SECRET  (or SUPABASE_JWT_SECRET)

# Required for payments
PAYSTACK_SECRET_KEY
PAYSTACK_PUBLIC_KEY
PAYSTACK_WEBHOOK_SECRET

# Required for notifications / email
ONESIGNAL_APP_ID
ONESIGNAL_API_KEY

# Required for background jobs
REDIS_URL
CELERY_BROKER_URL
CELERY_RESULT_BACKEND
```

Optional but recommended to set:
```
APP_NAME              # Your platform name
APP_TAGLINE           # Sign-off line in emails
EMAIL_FROM            # Sender email
EMAIL_FROM_NAME       # Sender display name
FRONTEND_URL          # Your mobile/web frontend URL
CORS_ORIGINS          # Comma-separated allowed origins
HP_CURRENCY_NAME      # Your loyalty currency name
```

### `app/messages.py` — Edit for wording changes

All user-facing text strings live here. Edit this file to change:
- Notification push titles and bodies (e.g. `ORDER_CONFIRMED_TITLE`, `BIRTHDAY_BODY`)
- Email subjects (e.g. `EMAIL_ORDER_CONFIRMED`)
- Error messages returned by the API
- Any other text the user or admin sees

> `{platform}` in any MSG string is replaced at runtime with `APP_NAME` from config.  
> `{currency}` is replaced with `HP_CURRENCY_NAME` from config.  
> Never put the brand name as a literal in `messages.py` — use `{platform}`.

---

## 3 · Notification Format — What Users Actually Receive

No notification sends a raw JSON body to a user. Every channel is formatted:

| Channel | Format |
|---------|--------|
| **Push** | OneSignal push with `headings: {en: title}` and `contents: {en: body}` |
| **Email** | OneSignal transactional email — HTML with `<p>Hi {name},</p><p>{body}</p>` |
| **In-app** | Row in `notifications` table (fetched by mobile app) with `title`, `body`, `channel="in_app"` |

The `{platform}` and `{currency}` placeholders in notification strings are resolved in two places:
1. `app/services/notification_service.py → send_notification()` (push + in-app)
2. `app/utils/email.py → send_email()` (email channel)

---

## 4 · Quick Checklist Before Deploying

- [ ] `SECRET_KEY` — random string, at least 32 chars
- [ ] `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY` — from Supabase dashboard
- [ ] `JWT_SECRET` — matches Supabase JWT secret exactly
- [ ] `PAYSTACK_SECRET_KEY`, `PAYSTACK_PUBLIC_KEY`, `PAYSTACK_WEBHOOK_SECRET`
- [ ] `ONESIGNAL_APP_ID`, `ONESIGNAL_API_KEY`
- [ ] `REDIS_URL` (and optionally `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`)
- [ ] `APP_NAME`, `APP_TAGLINE` — your brand name
- [ ] `EMAIL_FROM`, `EMAIL_FROM_NAME` — your verified sender address
- [ ] `FRONTEND_URL`, `CORS_ORIGINS` — your production frontend URL
