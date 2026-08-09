# Holy Grills — API Field Reference

Every field accepted or returned by the API, in one place. Use this to validate input before sending, understand error messages, and build frontend forms that match exactly what the backend expects.

---

## Table of Contents

1. [Global Rules](#global-rules)
2. [Enum Master List](#enum-master-list)
3. [Auth](#auth)
4. [Orders](#orders)
5. [Holy Points (HP)](#holy-points-hp)
6. [Wallet](#wallet)
7. [Menu](#menu)
8. [Cart & Saved for Later](#cart--saved-for-later)
9. [Marketplace](#marketplace)
10. [Events](#events)
11. [Rewards](#rewards)
12. [Challenges](#challenges)
13. [Referrals](#referrals)
14. [Leaderboard](#leaderboard)
15. [Order Locks](#order-locks)
16. [Notifications & Push](#notifications--push)
17. [Storefront & Promos](#storefront--promos)
18. [Riders](#riders)
19. [Kitchen](#kitchen)
20. [Admin](#admin)
21. [Webhooks](#webhooks)
22. [Health](#health)
23. [Error Response Shape](#error-response-shape)

---

## Global Rules

| Rule | Detail |
|------|--------|
| **Base path** | All endpoints are prefixed with `/api` |
| **Content-Type** | `application/json` for all request bodies |
| **Authentication** | `Authorization: Bearer <access_token>` header |
| **IDs** | All entity IDs are UUIDs (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`) |
| **Timestamps** | ISO-8601 format: `2024-11-15T10:30:00+00:00` or `2024-11-15T10:30:00Z` |
| **Dates** | ISO date format: `YYYY-MM-DD` (e.g. `2024-11-15`) |
| **Currency** | All monetary amounts are in Nigerian Naira (₦), expressed as numbers |
| **Phone numbers** | Nigerian format only — see [Phone](#phone-number) below |
| **Ordering window** | Orders accepted 08:00–16:00 WAT (configurable) |
| **Swagger UI** | Available at `/api/docs/` |

### Phone Number

- **Pattern**: Nigerian numbers only
- **Accepted formats**: `08012345678`, `+2348012345678`, `2348012345678`
- **Regex**: `^(\+?234|0)[789]\d{9}$`
- Must start with `07`, `08`, or `09` (after stripping country code)
- Spaces, dashes, and parentheses are stripped before validation

### Password

- Minimum **8 characters**
- Must contain at least **1 letter** and **1 digit**

---

## Enum Master List

Quick reference for all string fields that only accept a fixed set of values.

| Field | Allowed Values |
|-------|---------------|
| `role` | `student` · `admin` · `kitchen` · `rider` · `super_admin` |
| `payment_method` | `wallet` · `card` · `split` |
| `order_status` | `received` · `preparing` · `ready` · `assigned` · `out_for_delivery` · `delivered` · `cancelled` · `refunded` · `delivery_attempted` · `unclaimed` |
| `listing_type` | `code` · `service` · `product` · `experience` |
| `listing_status` | `pending` · `approved` · `rejected` · `draft` · `active` · `archived` |
| `discount_type` | `percentage` · `flat` |
| `promo_scope` | `cart` · `item` |
| `reward_category` | `food` · `merch` · `experience` · `marketplace` |
| `redemption_status` | `pending` · `fulfilled` · `rejected` |
| `platform` (push) | `ios` · `android` · `web` |
| `lock_status` | `active` · `cancelled` · `used` |
| `hp_transaction_type` | `earned` · `spent` · `expired` · `transferred_in` · `transferred_out` · `pending` · `unlocked` |
| `notification_channel` | `push` · `in_app` · `email` |
| `order_urgency` | `high` *(delivery_attempted only — indicates time-sensitive push)* |
| `section_type` (storefront) | `hero` · `banner` · `promo` · `faq` *(or any string — not constrained)* |
| `catering_status` | `pending` · `reviewed` · `confirmed` · `rejected` |
| `gift_status` | `pending` · `claimed` · `returned` |
| `withdrawal_status` | ~~`pending` · `processing` · `completed` · `failed`~~ — **withdrawal feature removed** |
| `batch_status` (delivery) | `pending` · `active` · `completed` · `cancelled` |

---

## Auth

### POST `/api/auth/register`

No authentication required.

**Request body**

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `email` | string | ✅ | Valid email format |
| `password` | string | ✅ | Min 8 chars, ≥1 letter, ≥1 digit |
| `full_name` | string | ✅ | Non-empty |
| `phone` | string | ❌ | Nigerian format — see [Phone](#phone-number) |
| `date_of_birth` | string (date) | ❌ | `YYYY-MM-DD`; must be ≥16 years old |
| `referred_by_code` | string | ❌ | Referral code from another user |

**Response `201`**
```json
{
  "user": { "id": "uuid", "email": "...", "full_name": "...", "role": "student" },
  "access_token": "eyJ...",
  "refresh_token": "eyJ..."
}
```

---

### POST `/api/auth/login`

**Request body**

| Field | Type | Required |
|-------|------|----------|
| `email` | string | ✅ |
| `password` | string | ✅ |

**Response `200`** — same shape as register.

---

### POST `/api/auth/refresh`

**Request body**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `refresh_token` | string | ✅ | JWT refresh token |
| `access_token` | string | ❌ | Current access token (enables silent rotation optimisation) |

**Response `200`**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "rotated": true
}
```
`rotated: false` means the old refresh token is still valid and no new one was issued.

---

### GET `/api/auth/me`

Auth: Bearer token required.

**Response `200`**
```json
{
  "id": "uuid",
  "email": "...",
  "full_name": "...",
  "phone": "...",
  "role": "student",
  "date_of_birth": "YYYY-MM-DD",
  "hp_balance": { "active": 420, "pending": 80 },
  "tier": { "id": "uuid", "name": "Regular", "slug": "regular" },
  "wallet": { "balance": 5000.00, "virtual_account": { ... } },
  "referral_code": "ABC123",
  "is_active": true
}
```

---

### PATCH `/api/auth/profile`

Auth: Bearer token required.  
All fields optional — only send what you want to update.

| Field | Type | Constraints |
|-------|------|-------------|
| `full_name` | string | Non-empty |
| `phone` | string | Nigerian format |
| `date_of_birth` | string (date) | `YYYY-MM-DD`; ≥16 years old |
| `push_enabled` | boolean | — |
| `email_notifications` | boolean | — |

---

### GET / POST `/api/auth/addresses`

**POST — Add address**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `label` | string | ✅ | e.g. `"Home"`, `"Hostel Block A"` |
| `address_line` | string | ✅ | Street address text |
| `city` | string | ✅ | — |
| `state` | string | ❌ | Defaults to Akure/Ondo |
| `landmark` | string | ❌ | Nearby landmark |
| `latitude` | number | ❌ | GPS coordinate |
| `longitude` | number | ❌ | GPS coordinate |
| `is_default` | boolean | ❌ | Set as default delivery address |

---

### POST `/api/auth/change-password`

| Field | Type | Required |
|-------|------|----------|
| `current_password` | string | ✅ |
| `new_password` | string | ✅ — min 8 chars, ≥1 letter, ≥1 digit |

---

### POST `/api/auth/device-token`

Register a push notification device token.

| Field | Type | Required | Allowed Values |
|-------|------|----------|----------------|
| `token` | string | ✅ | FCM / APNs device token |
| `platform` | string | ✅ | `ios` · `android` · `web` |
| `device_model` | string | ❌ | e.g. `"iPhone 15"` |

---

## Orders

### POST `/api/orders`

Auth: Optional Bearer token (guest checkout allowed).  
Orders only accepted during the ordering window (default **08:00–16:00 WAT**).

**Request body**

| Field | Type | Required | Constraints / Notes |
|-------|------|----------|---------------------|
| `items` | array | ✅ | At least 1 item — see [Order Item](#order-item) below |
| `delivery_window_id` | string (UUID) | ✅ | ID from `GET /orders/windows` |
| `payment_method` | string | ✅ | `wallet` · `card` · `split` |
| `delivery_address` | object | ✅ | See [Delivery Address](#delivery-address) below |
| `hp_points_to_redeem` | integer | ❌ | Must be ≤ active HP balance; min effective value 1 |
| `promo_code` | string | ❌ | Promo code string (case-insensitive) |
| `is_scheduled` | boolean | ❌ | `true` = future delivery window |
| `scheduled_for_window_id` | string (UUID) | ❌ | Required if `is_scheduled: true` |
| `is_squad_order` | boolean | ❌ | `true` = squad order (min 3 items for discount) |
| `guest_name` | string | ❌* | *Required if no auth token |
| `guest_phone` | string | ❌* | *Required if no auth token; Nigerian format |
| `paystack_reference` | string | ❌ | Required when `payment_method: "card"` or `"split"` |
| `wallet_amount` | number | ❌ | Amount from wallet when `payment_method: "split"` |

#### Order Item

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `menu_item_id` | string (UUID) | ✅ | Must be an active, available menu item |
| `quantity` | integer | ✅ | Min 1, max 50 per item |
| `addons` | array | ❌ | List of `{ addon_option_id: "uuid" }` |

#### Delivery Address

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `address_line` | string | ✅ | Full street address |
| `landmark` | string | ❌ | Nearby landmark to help rider |
| `zone` | string | ❌ | Delivery zone name — see `GET /orders/delivery-zones` |

#### Squad Order Rules

- `is_squad_order: true` qualifies when total item quantity ≥ **3** (configurable)
- Discount applied: delivery fee waived (100% by default)
- Optional subtotal discount (disabled by default)
- After order is created, add squad members via `POST /orders/{id}/squad-members`

---

### GET `/api/orders/windows`

No auth required. Returns available delivery windows.

**Response item fields**:
```json
{
  "id": "uuid",
  "label": "Lunch Window",
  "open_time": "10:00",
  "close_time": "13:00",
  "is_open": true,
  "date": "2024-11-15"
}
```

---

### GET `/api/orders/delivery-zones`

No auth required. Returns delivery zones and their fees.

**Response item fields**:
```json
{
  "id": "uuid",
  "name": "Zone A — Main Campus",
  "delivery_fee": 200.00,
  "estimated_minutes": 20
}
```

---

### PATCH `/api/orders/{order_id}/status`

Auth: Role `admin`, `kitchen`, or `rider`.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `status` | string | ✅ | Must be a valid next status — see [Order State Machine](#order-state-machine) |
| `notes` | string | ❌ | Free-text note stored in status log |

#### Order State Machine

```
received → preparing → ready → assigned → out_for_delivery → delivered
                                                           → delivery_attempted → delivered
                                                                               → unclaimed
Any pre-delivery state → cancelled → refunded
```

Only the immediately next state(s) in the graph are valid from any given state.

---

### POST `/api/orders/{order_id}/walk`

Auth: Role `admin`, `kitchen`, or `rider`.  
Walks an order through multiple status steps in one call (BFS shortest path).

| Field | Type | Required |
|-------|------|----------|
| `target_status` | string | ✅ — any valid downstream status |
| `notes` | string | ❌ |

---

### POST `/api/orders/{order_id}/cancel`

Auth: Bearer token (order owner) or admin.  
Only allowed while status is `received` and within the cancel window.

| Field | Type | Required |
|-------|------|----------|
| `reason` | string | ❌ |

---

### POST `/api/orders/{order_id}/review`

Auth: Bearer token. Order must be `delivered`.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `rating` | integer | ✅ | 1–5 |
| `kitchen_rating` | integer | ❌ | 1–5 |
| `rider_rating` | integer | ❌ | 1–5 |
| `comment` | string | ❌ | Free text |

---

### POST `/api/orders/{order_id}/squad-members`

Auth: Bearer token (order owner only).

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `emails` | array of strings | ✅ | Email addresses of squad members |

- Registered users receive an in-app `squad_order` notification
- Unregistered users receive an email invite with a referral link

---

### POST `/api/orders/{order_id}/share-hp`

Auth: Bearer token. Trigger HP sharing among squad members after delivery.

No request body required. HP is split equally among `squad_members` rows for the order.

---

## Holy Points (HP)

### HP Economy Summary

| Rule | Value |
|------|-------|
| Earn rate (food) | 0.1 HP per ₦1 spent (i.e. 1 HP per ₦10) |
| HP liability value | ₦0.185 per HP |
| Pending unlock rate | 30% of HP earned per order is unlocked per ₦1,000 food spend |
| Pending ceiling | Max pending = 35% of active balance (min floor: 200 HP) |
| Spin wheel cost | 10 HP per spin |
| HP expiry | After **120 days** of inactivity; 10%/month decay; warnings at day 70, 95, 118 |

### Tier Multipliers

| Tier | Slug | HP Multiplier |
|------|------|---------------|
| Starter | `starter` | 1.0× |
| Regular | `regular` | 1.1× |
| Champion | `champion` | 1.25× |
| Elite | `elite` | 1.5× |

### HP Bonuses

| Event | HP Amount |
|-------|-----------|
| Sign-up bonus | 0 (disabled by default) |
| First order delivered | 50 HP (welcome bonus) |
| Review submitted | 20 HP |
| Referral (per referral) | 75 HP (active) |
| Referral milestone — 5 referrals | 150 HP |
| Referral milestone — 10 referrals | 400 HP |
| Event check-in | 40 HP (pending) |
| Birthday | 150 HP |
| Wallet top-up ≥ ₦3,000 | 50 HP |
| Subscription | 50 HP |
| Social share | 25 HP |
| Marketplace purchase | 50 HP |

---

### GET `/api/hp/balance`

Auth: Bearer token.

**Response**
```json
{
  "active": 420,
  "pending": 80,
  "total": 500,
  "pending_ceiling": 147,
  "tier": { "name": "Regular", "multiplier": 1.1 }
}
```

---

### POST `/api/hp/transfer`

Auth: Bearer token.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `recipient_id` | string (UUID) | ✅ | Must be a different user |
| `amount` | integer | ✅ | Min 10; cannot exceed active HP balance |
| `notes` | string | ❌ | Reason for transfer |

---

### POST `/api/hp/bundles/purchase`

Purchase HP directly with card.

Auth: Bearer token.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `hp_amount` | integer | ✅ | Min 100 |
| `paystack_reference` | string | ✅ | Reference from a successful Paystack payment |

Pricing: ₦5 per HP.

---

The regular HP spin, daily free spin, and spin history endpoints have been
retired. There is no `/api/hp/spin` endpoint.

---

### GET `/api/hp/history`

Auth: Bearer token.

Query params: `page`, `per_page`, `type` (hp_transaction_type enum)

---

### POST `/api/hp/flash/redeem`

Auth: Bearer token.  
Flash deals: 50% discount, max 5 redemptions per window.

| Field | Type | Required |
|-------|------|----------|
| `listing_id` | string (UUID) | ✅ |

---

## Wallet

### GET `/api/wallet`

Auth: Bearer token.

**Response**
```json
{
  "balance": 5000.00,
  "virtual_account": {
    "account_number": "0123456789",
    "bank_name": "Wema Bank",
    "account_name": "Holy Grills / John Doe"
  }
}
```

---

### POST `/api/wallet/fund/bank`

Request a virtual account for bank transfer.  
Auth: Bearer token.

No request body. Returns virtual account details.

---

### POST `/api/wallet/fund/card`

Fund wallet by card via Paystack.  
Auth: Bearer token.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `amount` | number | ✅ | Min ₦100 |
| `callback_url` | string | ❌ | URL to redirect after Paystack checkout |

**Response**
```json
{
  "authorization_url": "https://checkout.paystack.com/...",
  "access_code": "...",
  "reference": "HG_abc123"
}
```

---

### POST `/api/wallet/withdraw` — REMOVED

> ⚠️ **Wallet withdrawal has been removed from the platform.** This endpoint returns 404. Do not implement withdrawal UI.

---

### POST `/api/wallet/transfer`

Transfer wallet balance to another user.  
Auth: Bearer token.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `recipient_id` | string (UUID) | ✅ | Must be a different active user |
| `amount` | number | ✅ | Must not exceed wallet balance |
| `note` | string | ❌ | — |

---

## Menu

### GET `/api/menu`

No auth required. Returns categories with their items.

**Item fields in response**:

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | — |
| `name` | string | — |
| `description` | string | — |
| `price` | number | In Naira |
| `hp_earn_value` | number | HP earned when ordered |
| `is_available` | boolean | `false` = sold out |
| `image_url` | string | — |
| `category_id` | UUID | — |
| `addon_groups` | array | See [Addon Group](#addon-group) |
| `daily_order_capacity` | integer \| null | Max orders per day; null = unlimited |
| `daily_orders_placed` | integer | Orders placed today |

#### Addon Group

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | — |
| `name` | string | e.g. `"Extras"`, `"Protein"` |
| `min_select` | integer | Minimum options customer must pick |
| `max_select` | integer | Maximum options customer may pick |
| `is_required` | boolean | Derived from `min_select > 0` |
| `options` | array | Each: `{ id, name, price_delta }` |

---

## Cart & Saved for Later

### POST `/api/cart`

Add item to cart.  
Auth: Bearer token.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `menu_item_id` | string (UUID) | ✅ | Must be active and available |
| `quantity` | integer | ✅ | Min 1 |
| `addons` | array | ❌ | `[{ "addon_option_id": "uuid" }]` |

---

### PATCH `/api/cart/{item_id}`

Update cart item quantity.

| Field | Type | Required |
|-------|------|----------|
| `quantity` | integer | ✅ — set to 0 to remove |

---

### POST `/api/cart/{item_id}/save`

Move cart item to saved-for-later. No body required.

---

### POST `/api/saved/{item_id}/restore`

Move saved item back to cart. No body required.

---

## Marketplace

### GET `/api/marketplace`

No auth required.

Query params: `category` (listing_type enum), `page`, `per_page`

---

### POST `/api/marketplace/{listing_id}/purchase`

Auth: Bearer token.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `use_hp_pricing` | boolean | ✅ | `true` = pay with HP; `false` = pay normal price |
| `payment_method` | string | ✅ | `wallet` · `card` · `split` |
| `wallet_amount` | number | ❌ | Required for `split` — amount from wallet |
| `payment_reference` | string | ❌ | Required for `card` or `split` — Paystack reference |

**Business rules**:
- HP pricing uses the `hp_price` on the listing
- For `code` type listings, a code is assigned from inventory; if stock ≤ 5 an admin alert fires
- Card/split payment must be verified against Paystack before code is assigned

---

### POST `/api/marketplace/requests`

Submit a vendor request (no auth needed).

| Field | Type | Required |
|-------|------|----------|
| `vendor_name` | string | ✅ |
| `vendor_email` | string | ✅ |
| `service_title` | string | ✅ |
| `category` | string | ✅ |
| `description` | string | ✅ |
| `proposed_price` | number | ❌ |

---

### Admin — POST `/api/admin/marketplace/listings`

Auth: Role `admin`.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `title` | string | ✅ | — |
| `listing_type` | string | ✅ | `code` · `service` · `product` · `experience` |
| `price` | number | ✅ | Normal price in Naira |
| `description` | string | ❌ | — |
| `hp_price` | integer | ❌ | HP cost when using HP pricing |
| `image_url` | string | ❌ | — |
| `is_active` | boolean | ❌ | Default `true` |
| `vendor_id` | string (UUID) | ❌ | — |

---

### Admin — POST `/api/marketplace/admin/codes/{listing_id}`

Upload access codes for a listing.  
Auth: Role `admin`.

| Field | Type | Required |
|-------|------|----------|
| `codes` | array of strings | ✅ |

---

## Events

### GET `/api/events`

No auth required. Returns active/upcoming events.

---

### POST `/api/events/{event_id}/register`

Auth: Bearer token.

No body required. Returns:
```json
{ "ticket_id": "uuid", "event_id": "uuid", "registered_at": "..." }
```

---

### POST `/api/events/{event_id}/checkin`

Auth: Bearer token.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `qr_token` | string | ✅ | Token from `GET /events/{id}/qr` (admin-generated) |

**On success**: Awards **40 HP** to the pending pool.

---

### POST `/api/events/{event_id}/qr`

Auth: Role `admin`. Generates a QR check-in token for the event.

No body required. Returns `{ "qr_payload": "..." }`.

---

### POST `/api/events/catering-requests`

No auth required.

| Field | Type | Required |
|-------|------|----------|
| `organizer_name` | string | ✅ |
| `email` | string | ✅ |
| `phone` | string | ✅ — Nigerian format |
| `event_name` | string | ✅ |
| `event_date` | string (date) | ✅ — `YYYY-MM-DD`; must be in the future |
| `expected_guests` | integer | ✅ |
| `budget` | number | ❌ |
| `notes` | string | ❌ |

---

### Admin — POST `/api/events`

Auth: Role `admin`.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `title` | string | ✅ | — |
| `description` | string | ❌ | — |
| `event_date` | string (ISO datetime) | ✅ | — |
| `location` | string | ❌ | — |
| `capacity` | integer | ❌ | Max registrations |
| `hp_reward` | integer | ❌ | HP awarded on check-in (overrides default 40) |
| `image_url` | string | ❌ | — |
| `assigned_to` | string (UUID) | ❌ | Staff user managing the event |

---

## Rewards

### GET `/api/rewards`

No auth required. Returns active rewards.

**Response item fields**: `id`, `title`, `description`, `hp_cost`, `category` (reward_category enum), `image_url`, `stock` (null = unlimited)

---

### POST `/api/rewards/{reward_id}/redeem`

Auth: Bearer token. Must have ≥ `hp_cost` active HP.

No body required. Returns:
```json
{
  "redemption_id": "uuid",
  "status": "pending",
  "hp_spent": 500,
  "fulfilment_eta_hours": 24
}
```

---

### Admin — PATCH `/api/rewards/admin/redemptions/{redemption_id}`

Auth: Role `admin`.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `status` | string | ✅ | `fulfilled` · `rejected` |
| `fulfilled_at` | string (ISO datetime) | ❌ | Defaults to now when `status: "fulfilled"` |
| `rejection_reason` | string | ❌ | Required when `status: "rejected"` |

---

### Admin — POST `/api/rewards`

Auth: Role `admin`.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `title` | string | ✅ | — |
| `hp_cost` | integer | ✅ | Min 1 |
| `category` | string | ✅ | `food` · `merch` · `experience` · `marketplace` |
| `description` | string | ❌ | — |
| `image_url` | string | ❌ | — |
| `stock` | integer | ❌ | null = unlimited |
| `is_active` | boolean | ❌ | Default `true` |

---

## Challenges & badges (retired)

The challenge, milestone, and badge subsystem has been retired. The
`/api/challenges` prefix is no longer registered, and existing database
definitions are deactivated by the cleanup migration.

---

## Referrals

### GET `/api/referrals`

Auth: Bearer token. Returns the current user's referral stats.

**Response**
```json
{
  "referral_code": "ABC123",
  "total_referrals": 3,
  "total_hp_earned": 225,
  "milestones": [
    { "count": 5, "hp_bonus": 150, "achieved": false },
    { "count": 10, "hp_bonus": 400, "achieved": false }
  ]
}
```

---

### POST `/api/referrals/record`

Admin/internal use — record that a referral converted.

| Field | Type | Required |
|-------|------|----------|
| `referred_user_id` | string (UUID) | ✅ |
| `order_id` | string (UUID) | ✅ |

---

## Leaderboard

### GET `/api/leaderboard`

No auth required.

Query params: `period` (`weekly` · `monthly` · `all_time`), `limit` (default 10)

**Response item fields**: `rank`, `user_id`, `full_name`, `hp_total`, `tier_name`, `avatar_url`

---

### GET `/api/leaderboard/hall-of-fame`

No auth required. Returns past monthly winners from `leaderboard_snapshots`.

---

### Admin — POST `/api/admin/cron/reset-monthly-leaderboard`

Auth: Role `admin`. Manually trigger the monthly reset.

No body required.

**On success**:
- Top 10 archived to `leaderboard_snapshots`
- Each winner receives a `leaderboard_rank` notification
- #1 receives special top-rank message

---

## Order Locks

Order locks let a user commit to ordering on a specific future date and lock in a discount.

### GET `/api/order-locks`

Auth: Bearer token. Returns the user's active locks.

---

### POST `/api/order-locks`

Auth: Bearer token.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `locked_date` | string (date) | ✅ | `YYYY-MM-DD`; must be a future date |
| `discount_pct` | number | ❌ | 1–50 (default 10); max enforced by config |

**Response `201`**
```json
{
  "lock": {
    "id": "uuid",
    "locked_date": "2024-12-01",
    "discount_pct": 10.0,
    "status": "active",
    "reschedule_count": 0
  }
}
```

---

### PATCH `/api/order-locks/{lock_id}/reschedule`

Auth: Bearer token (lock owner).  
Only allowed **once per lock** (`reschedule_count` must be 0).

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `locked_date` | string (date) | ✅ | `YYYY-MM-DD`; must be a future date |

---

### DELETE `/api/order-locks/{lock_id}`

Auth: Bearer token (lock owner). Cancels the lock.

No body required.

---

## Notifications & Push

### GET `/api/notifications`

Auth: Bearer token. Returns in-app notifications for the current user.

Query params: `unread_only` (bool), `page`, `per_page`

**Response item fields**:

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | — |
| `type` | string | See notification types below |
| `channel` | string | `push` · `in_app` · `email` |
| `title` | string | — |
| `body` | string | — |
| `is_read` | boolean | — |
| `action_url` | string | Deep-link URL |
| `metadata` | object | Includes `reference_id`, `reference_type`, `urgency` |
| `created_at` | ISO datetime | — |

#### `metadata.urgency`

| Value | Meaning |
|-------|---------|
| `null` / absent | Normal priority |
| `"high"` | Time-sensitive — front-end should surface immediately (e.g. modal/banner); only set for `order_delivery_attempted` |

#### Notification Types

| `type` value | Trigger |
|---|---|
| `order_confirmed` | Order placed |
| `order_preparing` | Kitchen starts prep |
| `order_ready` | Order ready for pickup |
| `order_assigned` | Rider assigned |
| `order_out_for_delivery` | Rider picked up |
| `order_delivered` | Delivered |
| `order_delivery_attempted` | Rider couldn't reach customer — **urgency: high** |
| `order_unclaimed` | Order not collected |
| `order_cancelled` | Order cancelled |
| `order_refunded` | Refund issued |
| `hp_earned` | HP credited |
| `hp_unlocked` | Pending HP unlocked |
| `tier_upgrade` | Reached a new tier |
| `tier_dropped` | Dropped a tier |
| `tier_grace_period` | Grace period started |
| `wallet_funded` | Wallet credited |
| `wallet_transfer` | Wallet transfer |
| `birthday_bonus` | Birthday HP awarded |
| `referral_hp_earned` | Referral HP credited |
| `leaderboard_rank` | Monthly leaderboard result |
| `squad_order` | Added to a squad order |
| `event_registered` | Event registration confirmed |
| `event_hp_pending` | Event check-in HP awarded |
| `marketplace_purchase` | Marketplace purchase confirmed |
| `reward_redemption` | Reward redemption status update |
| `abandoned_cart` | Cart recovery nudge |
| `share_prompt` | Social share HP prompt |
| `winback` | HP expiry warning |
| `first_order_gift` | First-order gift notification |

---

### PATCH `/api/notifications/{notification_id}/read`

Auth: Bearer token. Mark a notification as read.

No body required.

---

### PATCH `/api/notifications/preferences`

Auth: Bearer token.

| Field | Type | Notes |
|-------|------|-------|
| `push_enabled` | boolean | — |
| `email_notifications` | boolean | — |

---

### POST `/api/push/subscribe`

Register push notification subscription.  
Auth: Bearer token.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `subscription` | object | ✅ | Web Push subscription object OR OneSignal player object |

---

### DELETE `/api/push/subscribe`

Unregister push subscription.  
Auth: Bearer token. No body required.

---

## Storefront & Promos

### GET `/api/storefront/sections`

No auth required. Returns CMS homepage sections.

**Response item fields**: `id`, `key`, `title`, `section_type`, `content` (JSON), `sort_order`, `is_active`

---

### POST `/api/storefront/promo-codes/validate`

No auth required. Pre-validate a promo code before checkout.

| Field | Type | Required |
|-------|------|----------|
| `code` | string | ✅ |
| `order_subtotal` | number | ✅ — used to check `min_order_amount` |

**Response**
```json
{
  "valid": true,
  "discount_type": "percentage",
  "discount_value": 10,
  "discount_amount": 150.00
}
```

---

### POST `/api/storefront/subscribe`

Subscribe email to marketing updates.

| Field | Type | Required |
|-------|------|----------|
| `email` | string | ✅ |

---

### Admin — POST `/api/admin/promo-codes`

Auth: Role `admin`.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `code` | string | ✅ | Unique; uppercase recommended |
| `discount_type` | string | ✅ | `percentage` · `flat` |
| `discount_value` | number | ✅ | For `percentage`: 1–100; for `flat`: any positive number (₦) |
| `scope` | string | ❌ | `cart` (whole order) · `item` (per item); default `cart` |
| `min_order_amount` | number | ❌ | Minimum subtotal for code to apply |
| `max_uses` | integer | ❌ | null = unlimited |
| `expires_at` | string (ISO datetime) | ❌ | null = never expires |
| `description` | string | ❌ | — |

---

### Admin — POST `/api/storefront/sections`

Auth: Role `admin`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `key` | string | ✅ | Unique identifier slug |
| `title` | string | ✅ | Display title |
| `section_type` | string | ✅ | `hero` · `banner` · `promo` · `faq` (or any string) |
| `content` | object | ❌ | Free-form JSON payload |
| `sort_order` | integer | ❌ | — |
| `is_active` | boolean | ❌ | Default `true` |

---

## Riders

### GET `/api/riders/my-batch`

Auth: Role `rider`. Returns the rider's current delivery batch.

---

### POST `/api/riders/orders/{order_id}/pickup`

Auth: Role `rider`. Marks an order as picked up (`out_for_delivery`).

No body required.

---

### POST `/api/riders/orders/{order_id}/deliver`

Auth: Role `rider`. Marks an order as delivered.

No body required.

---

### POST `/api/riders/orders/{order_id}/attempt`

Auth: Role `rider`. Marks delivery as attempted (customer unreachable).  
Triggers a **high-urgency** push + in-app + email notification to the customer.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `notes` | string | ❌ | Default: `"Delivery attempted — customer unreachable"` |

---

### PATCH `/api/riders/availability`

Auth: Role `rider`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `is_available` | boolean | ✅ | `true` = online/ready; `false` = offline |
| `location_lat` | number | ❌ | GPS latitude |
| `location_lng` | number | ❌ | GPS longitude |

---

## Kitchen

### GET `/api/kitchen/orders`

Auth: Role `kitchen` or `admin`. Returns active orders for kitchen view.

---

### GET `/api/kitchen/scheduled`

Auth: Role `kitchen` or `admin`. Returns upcoming scheduled orders.

---

### PATCH `/api/kitchen/settings`

Auth: Role `admin`.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `settings` | object | ✅ | Key/value map of kitchen settings to update |

---

## Admin

### Admin — Users

#### PATCH `/api/admin/users/{user_id}/role`

| Field | Type | Required | Allowed Values |
|-------|------|----------|----------------|
| `role` | string | ✅ | `student` · `admin` · `kitchen` · `rider` · `super_admin` |

#### PATCH `/api/admin/users/{user_id}/status`

| Field | Type | Required |
|-------|------|----------|
| `is_active` | boolean | ✅ |

---

### Admin — HP

#### POST `/api/admin/hp/bulk-grant`

Auth: Role `admin`.

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `user_ids` | array of UUIDs | ✅ | — |
| `amount` | integer | ✅ | Positive integer |
| `reason` | string | ✅ | — |
| `hp_type` | string | ❌ | `active` (default) · `pending` |

---

### Admin — Delivery Batches

#### POST `/api/admin/delivery-batches`

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `rider_id` | string (UUID) | ✅ | Must have role `rider` |
| `order_ids` | array of UUIDs | ✅ | Orders to include in batch |
| `zone` | string | ❌ | Delivery zone |

---

### Admin — Cron Jobs (manual triggers)

| Endpoint | Effect |
|----------|--------|
| `POST /api/admin/cron/reset-monthly-leaderboard` | Archives top 10, notifies winners |
| `POST /api/admin/cron/hp-decay-check` | Runs HP expiry for inactive users |
| `POST /api/admin/cron/scan-abandoned-carts` | Marks inactive carts as abandoned |

No body required for any of these.

---

### Admin — System Settings

#### GET `/api/admin/settings`

Returns all system settings as `{ key, value, description }`.

#### POST `/api/admin/settings`

| Field | Type | Required |
|-------|------|----------|
| `key` | string | ✅ — must be unique |
| `value` | string | ✅ |
| `description` | string | ❌ |

#### PATCH `/api/admin/settings/{key}`

| Field | Type | Required |
|-------|------|----------|
| `value` | string | ✅ |

---

### Admin — Abandoned Carts

#### GET `/api/admin/abandoned-carts`

Returns carts marked abandoned (inactive for ≥60 minutes).

#### POST `/api/admin/abandoned-carts/{cart_id}/nudge`

Send recovery notification to cart owner. No body required.

---

### Admin — Gifts (First Order)

#### GET `/api/admin/gifts`

Returns gift records.

#### PATCH `/api/admin/gifts/{gift_id}`

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `status` | string | ✅ | `pending` · `claimed` · `returned` |

---

### Admin — Analytics

#### GET `/api/analytics/export`

Auth: Role `admin`.

Query param: `type` — one of `orders` · `hp` · `wallet` · `users`

Returns CSV or JSON export.

---

## Webhooks

### POST `/api/webhooks/paystack`

Paystack webhook — do **not** call this manually.

The request must include a `x-paystack-signature` header (HMAC-SHA512 of the raw body using `PAYSTACK_WEBHOOK_SECRET`). Requests with invalid or missing signatures are rejected with `400`.

**Events handled**:
- `charge.success` → credits wallet or confirms card payment
- `transfer.success` / `transfer.failed` → updates withdrawal status

---

### POST `/api/webhooks/flutterwave`

Flutterwave webhook — do **not** call this manually.

Verified via `verif-hash` header matching `FLUTTERWAVE_WEBHOOK_SECRET`.

---

## Health

### GET `/api/health`

No auth required.

**Response**
```json
{
  "api": "Holy Grills",
  "status": "ok",
  "version": "1.0.0",
  "checks": {
    "supabase": "connected",
    "redis": "connected"
  }
}
```

| `status` value | Meaning |
|----------------|---------|
| `ok` | All checks passing |
| `degraded` | One or more checks failed (API still functional) |

| `checks.*` value | Meaning |
|------------------|---------|
| `connected` | Service reachable |
| `not_configured` | Credentials not set (non-fatal) |
| `error:<detail>` | Connection failed |

---

## Error Response Shape

All errors follow this shape:

```json
{
  "error": "Short machine-readable label",
  "message": "Human-readable explanation",
  "request_id": "abc12345"
}
```

Include `request_id` when reporting bugs — it links to the server log entry.

### Common HTTP Status Codes

| Code | Meaning |
|------|---------|
| `200` | OK |
| `201` | Created |
| `400` | Bad request — field validation failed; check `message` for which field |
| `401` | Unauthorized — token missing or expired; refresh and retry |
| `403` | Forbidden — token valid but role insufficient |
| `404` | Not found |
| `405` | Method not allowed |
| `429` | Rate limited — back off and retry |
| `500` | Server error — unexpected; include `request_id` in bug report |

### Rate Limits (defaults — configurable via env)

| Endpoint | Limit |
|----------|-------|
| `POST /auth/register` | 10 requests / hour per IP |
| `POST /auth/login` | 20 requests / 15 min per IP |
| `POST /auth/refresh` | 30 requests / minute per IP |
| `POST /auth/verify-email` | 3 requests / hour per IP |
| `POST /auth/device-token` | 20 requests / hour per IP |
| `POST /auth/reset-password` | 5 requests / hour per IP |
