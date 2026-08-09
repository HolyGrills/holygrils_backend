# Holy Grills — API & Frontend Integration Guide

> **Version:** 1.0 — Phase 3  
> **Base URL (dev):** `https://<replit-dev-domain>/api`  
> **Auth:** All protected routes require `Authorization: Bearer <jwt>` header unless marked **public**.

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [User Profile](#2-user-profile)
3. [HP (HolyPoints) Economy](#3-hp-holypoints-economy)
4. [Menu & Cart](#4-menu--cart)
5. [Orders](#5-orders)
6. [Wallet](#6-wallet)
7. [Delivery Windows](#7-delivery-windows)
8. [Events & Ticket Tiers](#8-events--ticket-tiers)
9. [Leaderboard & Hall of Fame](#9-leaderboard--hall-of-fame)
10. [Badges & Challenges](#10-badges--challenges)
11. [Referrals](#11-referrals)
12. [Rewards Marketplace](#12-rewards-marketplace)
13. [Squads](#13-squads)
14. [Daily Check-in](#14-daily-check-in)
15. [Free Side Credits](#15-free-side-credits)
16. [Exclusive Spin](#16-exclusive-spin)
17. [Notifications](#17-notifications)
18. [Admin Panel](#18-admin-panel)
19. [Feature Flags](#19-feature-flags)
20. [Error Format](#20-error-format)

---

## 1. Authentication

All auth operations live under `/api/auth/`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/signup` | Public | Register new user |
| POST | `/auth/login` | Public | Login, returns JWT |
| POST | `/auth/logout` | ✅ | Invalidate session |
| POST | `/auth/refresh` | ✅ | Rotate JWT |
| POST | `/auth/forgot-password` | Public | Send reset email |
| POST | `/auth/reset-password` | Public | Set new password via token |
| GET  | `/auth/me` | ✅ | Authenticated user profile |
| PATCH | `/auth/me` | ✅ | Update profile fields |
| POST | `/auth/me/change-password` | ✅ | Change password |
| DELETE | `/auth/me` | ✅ | Delete account (GDPR) |

### Signup body
```json
{
  "full_name": "Amaka Obi",
  "phone": "08011112222",
  "email": "amaka@example.com",
  "password": "...",
  "referral_code": "JOHN123"
}
```

### Login response
```json
{
  "access_token": "<jwt>",
  "user": { "id": "...", "full_name": "...", "role": "customer", "hp_balance": 250 }
}
```

**Frontend notes:**
- Store `access_token` in memory (not localStorage) for XSS protection. Use a `refresh` call on app focus.
- On 401, auto-call `/auth/refresh`. If refresh fails → logout.
- Phone is the primary login identifier in the original flow; email is optional.

---

## 2. User Profile

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/auth/me` | ✅ | Full profile incl. HP, tier, wallet, referral code |
| PATCH | `/auth/me` | ✅ | Update `full_name`, `phone`, `email`, `avatar_url`, `birthday_date`, `department_id`, `academic_level_id` |
| GET | `/auth/me/addresses` | ✅ | Saved delivery addresses |
| POST | `/auth/me/addresses` | ✅ | Add address |
| PATCH | `/auth/me/addresses/<id>` | ✅ | Update address |
| DELETE | `/auth/me/addresses/<id>` | ✅ | Delete address |

### Profile object (key fields)
```json
{
  "id": "uuid",
  "full_name": "Amaka",
  "phone": "0801...",
  "role": "customer",
  "hp_balance": 450,
  "hp_earned_120day": 1200,
  "wallet_balance": 5000,
  "current_tier_id": "uuid",
  "referral_code": "AMAKA7F",
  "top4_finish_count": 1,
  "birthday_date": "1999-08-15",
  "graduation_claimed": false
}
```

---

## 3. HP (HolyPoints) Economy

### Balance & transactions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/hp/balance` | ✅ | Active + pending HP, 120-day earned |
| GET | `/hp/transactions` | ✅ | Transaction history (paginated) |
| POST | `/hp/transfer` | ✅ | Gift HP to another user |
| POST | `/hp/graduation-claim` | ✅ | One-time graduation HP bonus |

### Balance response
```json
{
  "active": 450,
  "pending": 120,
  "hp_earned_120day": 1200,
  "currency": "HP"
}
```

### HP earn events (triggered automatically by backend)
| Event | Type | Status |
|-------|------|--------|
| First order | `earn_first_order` | pending |
| Subsequent orders | `earn_order` | pending |
| Order delivered | pending → active conversion | active |
| Referral completed | `earn_referral` | active |
| Event check-in | `earn_event_checkin` | pending |
| Birthday | `earn_birthday` | active |
| Challenge/badge | `earn_challenge` | active |
| Daily check-in | `earn_daily_checkin` | active |

**Frontend notes:**
- Show pending HP as "Unlocks after delivery" with a lock icon.
- Poll `/hp/balance` after order status changes to `delivered`.

---

## 4. Menu & Cart

### Menu

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/menu` | Public | All published menu items |
| GET | `/menu/<id>` | Public | Single item detail |
| GET | `/menu/categories` | Public | Category list |

### Menu item object
```json
{
  "id": "uuid",
  "name": "Grilled Chicken",
  "description": "...",
  "price_naira": 2500,
  "price_hp": 150,
  "category_id": "uuid",
  "is_available": true,
  "image_url": "https://..."
}
```

### Cart

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/cart` | ✅ | Get current cart |
| POST | `/cart/items` | ✅ | Add item |
| PATCH | `/cart/items/<id>` | ✅ | Update quantity |
| DELETE | `/cart/items/<id>` | ✅ | Remove item |
| DELETE | `/cart` | ✅ | Clear cart |

**Frontend notes:**
- Show the HP equivalent price alongside the naira price.
- If user has free side credits (`/free-sides`), show a "🎁 Use free side" option on eligible items.

---

## 5. Orders

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/orders` | ✅ | Place order |
| GET | `/orders` | ✅ | My order history |
| GET | `/orders/<id>` | ✅ | Order detail + status |
| POST | `/orders/<id>/cancel` | ✅ | Cancel (within window) |
| POST | `/orders/<id>/review` | ✅ | Submit rating + review |

### Place order body
```json
{
  "delivery_window_id": "uuid",
  "address_id": "uuid",
  "items": [
    { "menu_item_id": "uuid", "quantity": 2, "customizations": "Extra spicy" }
  ],
  "free_side_choice": "Fries",
  "note": "...",
  "use_wallet": true,
  "use_hp": 100,
  "promo_code": "LAUNCH20"
}
```

### Order status flow
```
pending → confirmed → preparing → ready → assigned → out_for_delivery → delivered
                                                                    ↓
                                                               (HP unlocked)
```

**Frontend notes:**
- Display a live status bar with icons for each step.
- Once `delivered`, show confetti + "You earned X HP!" toast.
- If order has `is_squad_order: true`, show squad member list in order detail.

---

## 6. Wallet

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/wallet/balance` | ✅ | Current wallet balance |
| GET | `/wallet/transactions` | ✅ | Wallet transaction history |
| POST | `/wallet/topup` | ✅ | Initiate Paystack topup |
| POST | `/wallet/topup/verify` | ✅ | Verify Paystack callback |
| POST | `/wallet/withdraw` | ✅ | Withdrawal request |

---

## 7. Delivery Windows

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/delivery/windows` | Public | Available delivery windows |
| GET | `/delivery/windows/<id>` | Public | Window detail + capacity |

### Delivery window object
```json
{
  "id": "uuid",
  "label": "12:00 – 13:00",
  "day_of_week": "monday",
  "opens_at": "11:30",
  "closes_at": "12:00",
  "max_orders": 100,
  "current_orders": 42,
  "is_active": true
}
```

---

## 8. Events & Ticket Tiers

### Public event endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/events` | Public | Upcoming published events |
| GET | `/events/<id>` | Public | Event detail + check-in count |
| GET | `/events/<id>/tiers` | Public | Ticket tiers for event |
| POST | `/events/<id>/register` | ✅ | Register for event (optionally with tier_id) |
| POST | `/events/<id>/checkin` | ✅ | QR check-in (body: `{ "qr_token": "..." }`) |

### Register body
```json
{
  "tier_id": "uuid"
}
```
If no tiers exist for the event, `tier_id` is optional.

### Ticket tier object
```json
{
  "id": "uuid",
  "event_id": "uuid",
  "name": "VIP",
  "price_naira": 2000,
  "price_hp": 0,
  "capacity": 50,
  "sold_count": 12,
  "description": "Front-row seating + free drink"
}
```

### Catering requests

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/events/catering-requests` | Public | Submit catering/partnership request |
| GET | `/events/catering-requests` | Admin | List all requests |

### Admin event endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/events` | Admin | Create event |
| PATCH | `/events/<id>` | Admin | Update event |
| POST | `/events/<id>/tiers` | Admin | Create ticket tier |
| PATCH | `/events/tiers/<tier_id>` | Admin | Update tier |
| DELETE | `/events/tiers/<tier_id>` | Admin | Delete tier (blocked if tickets sold) |
| GET | `/events/<id>/registrants` | Admin | List registrants (add `?format=csv` for CSV download) |
| POST | `/events/<id>/send-registrants-to-host` | Admin | Email registrant list to organiser |

**Frontend notes:**
- If an event has ticket tiers, show a tier selection step before registration.
- Show `sold_count / capacity` as a progress bar. If `sold_count >= capacity`, disable registration for that tier.
- QR token is stored in the ticket object; generate a scannable QR from it client-side.

---

## 9. Leaderboard & Hall of Fame

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/leaderboard` | ✅ | Current month top earners |
| GET | `/leaderboard/hall-of-fame` | Public | Hall of Fame inductees |
| GET | `/leaderboard/squads` | ✅ | Squad leaderboard |
| GET | `/leaderboard/my-rank` | ✅ | Authenticated user's rank + HP this month |

### Monthly reset prizes (auto-assigned by backend)
| Rank | Free Side Credits | Exclusive Spin |
|------|------------------|----------------|
| #1 | 5 | ✅ |
| #2 | 3 | ✅ |
| #3 | 1 | ✅ |
| #4–#10 | — | ✅ |

**Frontend notes:**
- Leaderboard resets on the 1st of each month. Show a countdown timer to next reset.
- HoF threshold: user inducted after **3** top-3 monthly finishes.
- Show "🏅 Hall of Famer" badge on profiles of HoF inductees.

---

## 10. Badges & Challenges

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/challenges` | ✅ | All badges + current period challenges |
| POST | `/challenges/<id>/complete` | ✅ | Attempt challenge completion |

### Response structure
```json
{
  "badges": [
    { "id": "uuid", "title": "First Order", "earned": true, "earned_at": "2026-01-10T..." }
  ],
  "challenges_available": [
    { "id": "uuid", "title": "Order 3x This Week", "trigger_type": "order_count",
      "trigger_value": 3, "time_window": "weekly", "hp_awarded": 75, "completed_this_period": false }
  ],
  "challenges_completed": [ ... ]
}
```

### Trigger types (for UI progress bars)
| trigger_type | What to count |
|---|---|
| `order_count` | Delivered orders this period |
| `review_count` | Reviews submitted this period |
| `referral_count` | Completed referrals this period |
| `event_checkins` | Event check-ins this period |
| `squad_orders` | Squad orders this period |
| `order_distinct_days_weekly` | Distinct order days this week |
| `item_category` | Orders containing item from a category |
| `min_order_total` | Orders with total ≥ N naira |
| `hp_earned_total` | Total active HP earned (lifetime) |
| `membership_months` | Account age in months |
| `login_streak_cycles` | Consecutive login-streak weeks |
| `order_streak_weeks` | Consecutive order streak weeks |

**Frontend notes:**
- For `time_window: "weekly"` challenges, show progress bar resets Monday.
- For `time_window: "monthly"`, show progress bar resets 1st of month.
- `social_follow` trigger is self-declared — show a checkbox the user ticks.

---

## 11. Referrals

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/referrals` | ✅ | My referrals + completion status |
| GET | `/referrals/stats` | ✅ | Total referrals, HP earned from referrals |

### Referral object
```json
{
  "referee_name": "Chidi",
  "status": "completed",
  "hp_awarded": 75,
  "created_at": "2026-06-01T..."
}
```

### Referral milestones (auto-awarded)
| Referral count | HP bonus |
|---|---|
| 5 | 150 HP |
| 10 | 400 HP |
| 20 | 750 HP |
| 30 | 1,200 HP |
| 50 | 2,500 HP |

**Frontend notes:**
- Show `referral_code` prominently on the profile/referral page with a share button.
- Deep link: `https://app.holygrills.ng/signup?ref=AMAKA7F`

---

## 12. Rewards Marketplace

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/rewards` | ✅ | Available rewards (respects user's tier) |
| GET | `/rewards/<id>` | ✅ | Reward detail |
| POST | `/rewards/<id>/redeem` | ✅ | Redeem reward (deducts HP) |
| GET | `/rewards/my-redemptions` | ✅ | Redemption history |

### Reward object
```json
{
  "id": "uuid",
  "name": "Extra Side Dish",
  "description": "...",
  "hp_cost": 200,
  "tier_required": "silver",
  "stock": 50,
  "is_active": true
}
```

**Frontend notes:**
- Grey out rewards the user cannot afford or doesn't have the tier for.
- Show fulfilment ETA from `system_settings.reward_fulfilment_hours`.

---

## 13. Squads

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/orders/squad` | ✅ | Create squad order |
| GET | `/orders/squad/<id>` | ✅ | Squad order detail + member status |
| POST | `/orders/squad/<id>/join` | ✅ | Join a squad order |
| POST | `/orders/squad/<id>/lock` | ✅ | Lock and place squad order |

**Business logic:**
- Max items per squad order: **6** (configurable via `SQUAD_ORDER_MAX_ITEMS`).
- Squad leader gets bonus HP when the order is delivered.
- Squad members each earn their individual HP on delivery.

---

## 14. Daily Check-in

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/checkin` | ✅ | Record today's check-in (idempotent) |
| GET | `/checkin/history` | ✅ | Check-in history (last 30 days by default) |

### POST `/checkin` response
```json
{
  "message": "Daily check-in complete — 5 HP earned",
  "checkin_date": "2026-08-05",
  "hp_awarded": 5
}
```
If called again today:
```json
{
  "message": "You have already checked in today",
  "already_checked_in": true
}
```

### GET `/checkin/history` response
```json
{
  "checkins": [
    { "id": "uuid", "checkin_date": "2026-08-05", "created_at": "..." }
  ],
  "total": 30,
  "checked_in_today": true
}
```

**Frontend notes:**
- Show a ✅ button on the home screen. Disable it and mark as "Done!" once `checked_in_today` is true.
- HP amount is controlled by `system_settings.daily_checkin_hp` (default: 5 HP).
- Feature gate behind `feature_flags.daily_checkin` flag.

---

## 15. Free Side Credits

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/free-sides` | ✅ | My credit balance + available side options |
| POST | `/free-sides/redeem` | ✅ | Redeem one credit at checkout |

### GET `/free-sides` response
```json
{
  "total_credits": 3,
  "credits": [
    { "id": "uuid", "credits_remaining": 3, "source": "leaderboard_prize",
      "month": "2026-07", "expires_at": "2026-10-01T..." }
  ],
  "available_sides": ["Fries", "Coleslaw", "Plantain", "Gizzard"]
}
```

### POST `/free-sides/redeem` body
```json
{
  "side_choice": "Fries",
  "order_id": "uuid"
}
```

**Frontend notes:**
- Show free-side credit badge in cart if `total_credits > 0`.
- Allow user to pick one side from `available_sides` before checkout.
- Credits expire — show expiry date and countdown for urgency.
- Feature gate behind `feature_flags.free_sides`.

---

## 16. Exclusive Spin

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/exclusive-spin` | ✅ | My spin credits + prize table |
| POST | `/exclusive-spin/spin` | ✅ | Execute one spin |
| POST | `/exclusive-spin/buy` | ✅ | Purchase extra spin (costs HP) |

### GET `/exclusive-spin` response
```json
{
  "total_spins": 1,
  "spins": [
    { "id": "uuid", "spin_count": 1, "source": "leaderboard_prize",
      "expires_at": "2026-09-05T..." }
  ],
  "prizes": [
    { "name": "HP Jackpot +750", "weight": 5 },
    { "name": "HP Bolt +300",    "weight": 20 }
  ]
}
```

### POST `/exclusive-spin/spin` response
```json
{
  "message": "You spun and won: HP Bolt +300",
  "prize": "HP Bolt +300",
  "spins_remaining": 0
}
```

### POST `/exclusive-spin/buy` body
```json
{}
```
Cost: `EXCLUSIVE_SPIN_EXTRA_COST` HP (default 500). Response includes `cost_hp` and `expires_at`.

**Frontend notes:**
- Implement a wheel animation client-side; the winning prize is returned by the API.
- Show weights as visual segment sizes on the wheel.
- HP prizes are applied instantly; physical prizes (food items) are fulfilled by admin within 24h.
- Feature gate behind `feature_flags.exclusive_spin`.

---

## 17. Notifications

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/notifications` | ✅ | Notification inbox (paginated) |
| PATCH | `/notifications/<id>/read` | ✅ | Mark as read |
| PATCH | `/notifications/read-all` | ✅ | Mark all as read |
| POST | `/push/register` | ✅ | Register push token |

### Notification object
```json
{
  "id": "uuid",
  "type": "order_confirmed",
  "title": "Order Confirmed!",
  "body": "Your order #ABC123 is heading to the kitchen.",
  "is_read": false,
  "created_at": "...",
  "reference_id": "uuid",
  "reference_type": "order"
}
```

**Frontend notes:**
- Use `reference_type` + `reference_id` to deep-link the notification to the relevant screen.
- Show a badge count from `notifications?is_read=false`.

---

## 18. Admin Panel

All admin routes require `role: admin` in the JWT.

### Users
| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/users` | List users (supports `?q=`, `?role=`, `?limit=`, `?offset=`) |
| GET | `/admin/users/<id>` | User detail |
| PATCH | `/admin/users/<id>` | Update user (role, is_active, etc.) |
| POST | `/admin/users/<id>/grant-hp` | Award HP to user |
| POST | `/admin/users/<id>/deduct-hp` | Deduct HP from user |

### Orders
| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/orders` | All orders (filterable) |
| PATCH | `/admin/orders/<id>/status` | Update order status |

### Menu
| Method | Path | Description |
|--------|------|-------------|
| POST | `/menu` | Create menu item |
| PATCH | `/menu/<id>` | Update menu item |
| DELETE | `/menu/<id>` | Delete menu item |

### System Settings
| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/settings` | List all system_settings |
| PATCH | `/admin/settings/<key>` | Update a setting value |

### HP Economy
| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/hp/stats` | HP issued, spent, net, tier distribution |
| GET | `/admin/hp/transactions` | Filtered HP transaction log |

### Events (Admin)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/events` | Create event |
| PATCH | `/events/<id>` | Update event |
| POST | `/events/<id>/tiers` | Create ticket tier |
| PATCH | `/events/tiers/<tier_id>` | Update ticket tier |
| DELETE | `/events/tiers/<tier_id>` | Delete tier |
| GET | `/events/<id>/registrants` | List registrants (`?format=csv` for CSV) |
| POST | `/events/<id>/send-registrants-to-host` | Email list to organiser |

### Leaderboard Prize Fulfilment
| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/leaderboard-prizes` | List prize records (`?status=pending`) |
| PATCH | `/admin/leaderboard-prizes/<id>` | Mark as fulfilled/cancelled |

### Hall of Fame Box Rewards
| Method | Path | Description |
|--------|------|-------------|
| GET | `/admin/hall-of-fame-rewards` | List HoF reward records (`?status=pending`) |
| PATCH | `/admin/hall-of-fame-rewards/<id>` | Update status |

### Milestones (Admin)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/challenges/admin` | All milestones |
| POST | `/challenges/admin` | Create milestone |
| PATCH | `/challenges/admin/<id>` | Update milestone |
| POST | `/challenges/admin/<id>/grant/<user_id>` | Admin-grant to user |

---

## 19. Feature Flags

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/admin/feature-flags` | Admin | List all flags |
| GET | `/admin/feature-flags/<name>` | Admin | Get one flag |
| PATCH | `/admin/feature-flags/<name>` | Admin | Create or update flag |

### PATCH body
```json
{
  "is_active": false
}
```

### Default flags seeded by migration
| Flag | Default | Controls |
|------|---------|----------|
| `leaderboard_prizes` | ON | Auto-award prizes on monthly reset |
| `exclusive_spin` | ON | Exclusive spin routes enabled |
| `free_sides` | ON | Free side credit routes enabled |
| `daily_checkin` | ON | Daily check-in route enabled |
| `hall_of_fame` | ON | HoF induction on monthly reset |
| `squad_orders` | ON | Squad order feature |
| `event_ticket_tiers` | ON | Ticket tiers for events |
| `birthday_bonus` | ON | Birthday HP bonus |
| `referral_bonus` | ON | Referral HP awards |
| `order_streaks` | ON | Order streak milestone rewards |

**Frontend notes:**
- Fetch flags at app startup and cache for session duration.
- Gate all new feature UI behind the corresponding flag.
- Do not show UI elements for disabled flags — do not just disable them.

---

## 20. Error Format

All API errors return a consistent JSON envelope:

```json
{
  "error": "Human-readable error message",
  "message": "Optional detail (sometimes same as error)",
  "request_id": "abc12345"
}
```

### HTTP status codes
| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Resource created |
| 400 | Validation error / bad request |
| 401 | Not authenticated (missing or invalid JWT) |
| 403 | Forbidden (authenticated but insufficient role) |
| 404 | Resource not found |
| 409 | Conflict (duplicate, already exists) |
| 422 | Unprocessable entity (business logic rejection) |
| 500 | Internal server error |
| 502 | External service error (Resend, Paystack) |

---

## Appendix A — HP Earn Rate Reference

| Action | HP | Status | Notes |
|--------|----|--------|-------|
| Signup bonus | `SIGNUP_BONUS_HP` env | active | Configurable |
| Welcome bonus | `WELCOME_BONUS_HP` env | active | On first login after signup |
| Order (per ₦100) | Configurable per tier | pending → active on delivery | |
| Referral | `REFERRAL_HP` env | active | Per completed referral |
| Event check-in | `EVENT_CHECKIN_HP` env | pending | Unlocks after delivery |
| Review | `REVIEW_HP` env | pending | |
| Birthday | `BIRTHDAY_HP` env | active | |
| Daily check-in | `system_settings.daily_checkin_hp` | active | Default 5 HP |
| Social share | `SOCIAL_SHARE_HP` env | pending | Self-declared, requires moderation |
| Wallet top-up | `WALLET_TOPUP_HP` env | active | Per successful top-up |
| Challenge completion | varies | active | Per challenge `hp_awarded` |

---

## Appendix B — Environment Variables Summary

| Variable | Purpose |
|----------|---------|
| `RESEND_API_KEY` | Email delivery (required for emails) |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Backend DB access |
| `JWT_SECRET` | JWT signing key |
| `EXCLUSIVE_SPIN_EXTRA_COST` | HP cost for extra spin (default: 500) |
| `EXCLUSIVE_SPIN_VALIDITY_DAYS` | Spin credit expiry (default: 30) |
| `FREE_SIDE_CREDITS_VALIDITY_DAYS` | Free side expiry (default: 60) |
| `SQUAD_ORDER_MAX_ITEMS` | Max items per squad order (default: 6) |
| `EMAIL_FROM` | Resend sender address |
| `EMAIL_FROM_NAME` | Resend sender name |
| `APP_NAME` | Platform display name |
| `APP_TAGLINE` | Email footer tagline |
| `REDIS_URL` | Celery broker |
| `CELERY_BROKER_URL` | Celery broker |
| `CELERY_RESULT_BACKEND` | Celery result store |

---

*Last updated: 2026-08-05 | Holy Grills Engineering*
