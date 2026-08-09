# Holy Grills — Complete API Frontend Integration Guide

> **Version:** 2.0 | **Last updated:** August 2026
> **Stack:** Flask 3.x · Supabase · Paystack · Resend · OneSignal (push only)
> **Base URL (dev):** `http://localhost:5000/api`
> **Base URL (prod):** `https://<your-domain>/api`
> **API Docs (Swagger UI):** `/api/docs/`

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Email Configuration (Resend)](#2-email-configuration-resend)
3. [Notification Blasts](#3-notification-blasts)
4. [Feature Flags — Flip Any Feature](#4-feature-flags--flip-any-feature)
5. [Authentication](#5-authentication)
6. [Menu — Categories, Items, Variations & Add-Ons](#6-menu)
7. [Cart](#7-cart)
8. [Saved Items](#8-saved-items)
9. [Orders](#9-orders)
10. [HP Economy (Holy Points)](#10-hp-economy)
11. [Wallet](#11-wallet)
12. [Rewards](#12-rewards)
13. [Marketplace](#13-marketplace)
14. [Events](#14-events)
15. [Referrals](#15-referrals)
16. [Notifications](#16-notifications)
17. [Admin Panel](#17-admin-panel)
18. [Kitchen](#18-kitchen)
19. [Riders](#19-riders)
20. [Leaderboard, Hall of Fame & Prizes](#20-leaderboard)
21. [Challenges & Badges](#21-challenges--badges)
22. [Daily Check-In](#22-daily-check-in)
23. [Free Side Credits](#23-free-side-credits)
24. [Exclusive Spin](#24-exclusive-spin)
25. [Storefront](#25-storefront)
26. [Analytics](#26-analytics)
27. [Order Locks](#27-order-locks)
28. [Delivery Locations](#28-delivery-locations)
29. [Graduation](#29-graduation)
30. [Departments](#30-departments)
31. [Academic Levels](#31-academic-levels)
32. [Admin Gifts & System Settings](#32-admin-gifts--system-settings)
33. [Webhooks](#33-webhooks)
34. [Health Check](#34-health-check)
35. [User Flow Guides](#35-user-flow-guides)
    - 35a. Guest Order Flow
    - 35b. Authenticated Student Flow
    - 35c. Admin Flow
    - 35d. Kitchen Flow
    - 35e. Rider Flow

---

## 1. Quick Start

### Required Headers

```http
Content-Type: application/json
Authorization: Bearer <access_token>   # for all protected endpoints
```

### Authentication Model

All protected routes require a JWT in the `Authorization: Bearer <token>` header.

| Token | Lifetime | Purpose |
|-------|----------|---------|
| `access_token` | Configurable (default 1 hour) | API calls |
| `refresh_token` | Configurable (default 30 days) | Get new access token |

**On every 401:** call `POST /api/auth/refresh` with both tokens. If refresh fails, redirect to login.

### Standard Error Shape

```json
{ "error": "Human-readable message", "request_id": "abc12345" }
```

### Standard Pagination

All list endpoints accept:
- `?limit=20` (max 100 unless documented otherwise)
- `?offset=0`

---

## 2. Email Configuration (Resend)

**Where to configure:** Replit Secrets → `RESEND_API_KEY`

**Where to set sender identity:**
```
EMAIL_FROM       = noreply@holygrills.ng   # sender email address
EMAIL_FROM_NAME  = Holy Grills             # sender display name
```

**Email is sent automatically** by the backend for these critical events:
| Trigger | Template Key |
|---------|-------------|
| Order confirmed | `order_confirmed` |
| Order delivered | `order_delivered` |
| Order refunded | `order_refunded` |
| HP decay started | `hp_decay_applied` |
| HP decay warning | `hp_decay_warning` |
| Tier downgrade | `tier_downgrade` |
| Tier upgrade | `tier_upgrade` |
| Birthday HP | `birthday_bonus` |
| Wallet top-up (card) | `wallet_funded_card` |
| Wallet top-up (bank) | `wallet_funded_bank` |
| Password reset | `password_reset` |
| Referral completed | `referral_completed` |
| Reward fulfilled | `reward_fulfilled` |
| Event registration | `event_registered` |
| Account deleted | `account_deleted` |

**All email templates** live in `app/utils/email.py` → `TEMPLATES` dict.
To change subject or body wording, edit the template there.
To change user-facing string constants (error messages, notification text), edit `app/messages.py`.

**To send a raw email from admin** (e.g. registrant list to host):
```
POST /api/events/<event_id>/send-registrants-to-host
```

---

## 3. Notification Blasts

**Blast = push + in-app notification sent to all users (or a segment).**

### Send a Blast

```http
POST /api/notifications/blasts
Authorization: Bearer <admin_token>
```
```json
{
  "title": "🎉 New Menu Drop!",
  "body": "We just added 3 new combos. Order now before they sell out!",
  "segment": "all",
  "data": {}
}
```

### List All Blasts

```http
GET /api/notifications/blasts
Authorization: Bearer <admin_token>
```

### Get One Blast

```http
GET /api/notifications/blasts/<blast_id>
Authorization: Bearer <admin_token>
```

---

## 4. Feature Flags — Flip Any Feature

**Every feature in the system is controlled by a flag in the `feature_flags` table.**
No code deploy needed to turn a feature on or off — flip it from the admin API.

### List All Flags

```http
GET /api/admin/feature-flags
Authorization: Bearer <admin_token>
```

**Response:**
```json
[
  { "feature_name": "spin_and_win", "is_active": true, "description": "Enables HP spin wheel" },
  { "feature_name": "marketplace_general", "is_active": false, "description": "Opens marketplace" }
]
```

### Get One Flag

```http
GET /api/admin/feature-flags/<flag_name>
Authorization: Bearer <admin_token>
```

### Toggle / Update a Flag

```http
PATCH /api/admin/feature-flags/<flag_name>
Authorization: Bearer <admin_token>
```
```json
{ "is_active": false }
```

### All Available Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `leaderboard_prizes` | `true` | Prize payout logic after monthly reset |
| `free_side_credits` | `true` | Free side credit issuance at checkout |
| `exclusive_spin` | `true` | Exclusive spin for top-10 leaderboard |
| `hall_of_fame` | `true` | Hall of Fame data recording |
| `badge_system` | `false` | Retired — badges and milestone challenges are no longer available |
| `spin_and_win` | `false` | Retired — daily free spin and regular HP spin are no longer available |
| `marketplace_general` | `false` | Opens marketplace to students |
| `hp_transfer` | `false` | Peer-to-peer HP transfer |
| `flash_redemptions` | `false` | Time-limited HP discount drops |
| `squad_orders` | `true` | Squad ordering flow |
| `referral_milestones` | `false` | Retired — referral milestone bonuses are no longer available |
| `subscription_codes` | `false` | Subscription code redemption |
| `hp_expiry_warnings` | `true` | Depreciation warning push notifications |
| `birthday_hp` | `true` | Automatic birthday HP award job |
| `scheduled_orders` | `true` | Future order scheduling |
| `abandoned_cart_nudge` | `false` | Recovery nudge after 30 min inactivity |
| `daily_checkin` | `true` | Explicit daily check-in button |
| `event_ticket_tiers` | `true` | Multi-tier event ticket pricing |

---

## 5. Authentication

**Prefix:** `/api/auth`

---

### POST /api/auth/register

Register a new student account.

**Body:**
```json
{
  "email": "student@futa.edu.ng",
  "password": "SecurePass1!",
  "full_name": "Jane Doe",
  "phone": "08012345678",
  "date_of_birth": "2000-01-15",
  "referred_by": "JANE123",
  "department_id": "<uuid>",
  "academic_level_id": "<uuid>"
}
```

> Password rules: min 8 chars, 1 uppercase, 1 number, 1 special character.
> Phone: 11-digit Nigerian format (`08012345678` or `+2348012345678`).
> Age: must be 16+.

**Response 201:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": { "id": "uuid", "email": "...", "role": "student", "full_name": "..." }
}
```

**Errors:** `400` underage | invalid phone | duplicate email | weak password

---

### POST /api/auth/login

```json
{ "email": "...", "password": "..." }
```

**Response 200:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "user": { "id": "uuid", "email": "...", "role": "student", "full_name": "..." }
}
```

**Errors:** `401` wrong credentials | `429` rate-limited

---

### POST /api/auth/refresh

Rotate tokens. Send **both** current tokens; server issues new pair.

```json
{ "refresh_token": "eyJ...", "access_token": "eyJ..." }
```

**Response 200:**
```json
{ "access_token": "eyJ...", "refresh_token": "eyJ...", "rotated": true }
```

---

### GET /api/auth/me

Get current user profile. Auth required.

**Response 200:**
```json
{
  "id": "uuid",
  "email": "student@futa.edu.ng",
  "full_name": "Jane Doe",
  "phone": "08012345678",
  "role": "student",
  "tier": "bronze",
  "hp_balance": 450,
  "referral_code": "JANE123",
  "date_of_birth": "2000-01-15",
  "department_id": "uuid",
  "academic_level_id": "uuid"
}
```

---

### PATCH /api/auth/profile

Update own profile. Auth required.

```json
{
  "full_name": "Jane Doe Updated",
  "phone": "08012345678",
  "date_of_birth": "2000-01-15",
  "department_id": "<uuid>",
  "academic_level_id": "<uuid>"
}
```

---

### POST /api/auth/logout

Revokes the current session token. Auth required.

```json
{ "refresh_token": "eyJ..." }
```

---

### POST /api/auth/logout-all-devices

Revokes all sessions for this user on all devices. Auth required.

---

### GET /api/auth/addresses

List the authenticated user's saved delivery addresses.

**Response 200:** Array of address objects.

---

### POST /api/auth/addresses

Add a new saved address.

```json
{
  "label": "Room 14B",
  "hostel_id": "<uuid>",
  "notes": "Green door on the left"
}
```

---

### PATCH /api/auth/addresses/<address_id>

Update a saved address.

---

### DELETE /api/auth/addresses/<address_id>

Delete a saved address.

---

### POST /api/auth/change-password

```json
{ "current_password": "...", "new_password": "SecureNew1!" }
```

---

### DELETE /api/auth/account

Permanently delete the authenticated user's account. Irreversible.

```json
{ "password": "MyPassword1!" }
```

---

### POST /api/auth/verify-email

Resend email verification link.

```json
{ "email": "student@futa.edu.ng" }
```

---

### POST /api/auth/reset-password

Request a password reset email (public, no auth).

```json
{ "email": "student@futa.edu.ng" }
```

---

### POST /api/auth/device-token

Register a device push token (for OneSignal push notifications).

```json
{
  "token": "ExponentPushToken[...]",
  "platform": "ios"
}
```

---

### GET /api/auth/streak

Get the authenticated user's login streak and check-in status.

**Response 200:**
```json
{
  "current_streak": 7,
  "longest_streak": 14,
  "streak_start": "2026-07-28",
  "checked_in_today": true,
  "missed_days_this_week": 0
}
```

---

## 6. Menu

**Prefix:** `/api/menu`

---

### GET /api/menu/categories

List all active menu categories. Public.

**Response 200:** Array of `{ id, name, description, is_active, sort_order }`.

---

### POST /api/menu/categories *(Admin)*

```json
{
  "name": "Combos",
  "description": "Full meal combos",
  "sort_order": 1
}
```

---

### PATCH /api/menu/categories/<category_id> *(Admin)*

Update a category name, description, or sort order.

---

### DELETE /api/menu/categories/<category_id> *(Admin)*

Soft-deactivate a category (does not delete items inside it).

---

### GET /api/menu/items

List all available menu items. Public. Supports filters:

| Query param | Type | Description |
|-------------|------|-------------|
| `category_id` | UUID | Filter by category |
| `available_only` | bool | Default `true` — hides sold-out |
| `search` | string | Name search |
| `limit` | int | Default 50 |
| `offset` | int | Default 0 |

**Response 200:** Array of enriched item objects with `daily_sold`, `daily_remaining`, `at_capacity`.

---

### GET /api/menu/items/<item_id>

Get full item detail including **variation groups**, **options**, and **add-on groups**.

**Response 200:**
```json
{
  "id": "uuid",
  "name": "Chicken & Rice Combo",
  "price": 2500,
  "category_id": "uuid",
  "is_available": true,
  "daily_limit": 50,
  "daily_sold": 12,
  "variation_groups": [
    {
      "id": "uuid",
      "name": "Choose your side",
      "is_required": true,
      "min_selections": 1,
      "max_selections": 1,
      "options": [
        { "id": "uuid", "name": "Coleslaw", "price_delta": 0, "is_available": true },
        { "id": "uuid", "name": "Plantain", "price_delta": 200, "is_available": true }
      ]
    }
  ]
}
```

---

### POST /api/menu/items *(Admin)*

Create a new menu item.

```json
{
  "name": "Jollof Rice Combo",
  "price": 2000,
  "category_id": "<uuid>",
  "description": "Jollof rice with chicken",
  "daily_limit": 100,
  "is_available": true,
  "sort_order": 1
}
```

---

### PATCH /api/menu/items/<item_id> *(Admin)*

Update item price, availability, daily limit, description, etc.

```json
{
  "price": 2200,
  "is_available": false,
  "daily_limit": 80
}
```

---

### POST /api/menu/items/<item_id>/archive *(Admin)*

Archive (soft-delete) a menu item. Hides it from all listings.

---

### POST /api/menu/items/bulk-availability *(Admin)*

Toggle availability for multiple items at once.

```json
{
  "item_ids": ["uuid1", "uuid2"],
  "is_available": false
}
```

---

### Menu Item Variations (Admin)

Variations are **required or optional choices** tied to a specific menu item (e.g., "Choose your side"). Different from add-ons which are optional extras on any order.

#### GET /api/menu/items/<item_id>

Variation groups and options are returned in the item detail response (see above).

#### POST /api/menu/items/<item_id>/variation-groups *(Admin)*

Create a variation group on an item.

```json
{
  "name": "Choose your side",
  "is_required": true,
  "min_selections": 1,
  "max_selections": 1,
  "sort_order": 0
}
```

#### PATCH /api/menu/items/<item_id>/variation-groups/<group_id> *(Admin)*

Update a variation group (name, required flag, min/max selections).

#### DELETE /api/menu/items/<item_id>/variation-groups/<group_id> *(Admin)*

Delete a variation group and **all its options** (cascades).

---

#### POST /api/menu/items/<item_id>/variation-groups/<group_id>/options *(Admin)*

Add a choice to a variation group.

```json
{
  "name": "Coleslaw",
  "price_delta": 0,
  "is_available": true,
  "sort_order": 0
}
```

> `price_delta`: extra charge for this option (0 = free, 200 = +₦200).

#### PATCH /api/menu/items/<item_id>/variation-groups/<group_id>/options/<option_id> *(Admin)*

Update an option (name, price_delta, availability, sort_order).

#### DELETE /api/menu/items/<item_id>/variation-groups/<group_id>/options/<option_id> *(Admin)*

Delete a single variation option.

---

### Menu Add-Ons (Admin)

Add-ons are **optional extras** that apply to any order (not tied to a specific item).

#### GET /api/menu/items/<item_id>/addons

List add-on groups attached to a specific item.

#### GET /api/menu/addons

List all global add-on items.

#### POST /api/menu/addons *(Admin)*

Create a global add-on.

```json
{
  "name": "Extra Sauce",
  "price": 100,
  "category": "sauce",
  "is_available": true
}
```

#### PATCH /api/menu/addons/<addon_id> *(Admin)*

Update an add-on.

#### POST /api/menu/addons/<addon_id>/archive *(Admin)*

Archive an add-on.

---

#### POST /api/menu/items/<item_id>/addon-groups *(Admin)*

Create an add-on group linked to a specific item.

```json
{
  "name": "Sides",
  "is_required": true,
  "min_select": 3,
  "max_select": 3
}
```

#### PATCH /api/menu/items/<item_id>/addon-groups/<group_id> *(Admin)*

Update an add-on group.

#### DELETE /api/menu/items/<item_id>/addon-groups/<group_id> *(Admin)*

Delete an add-on group and all its linked add-ons (cascades).

---

### Kitchen Capacity *(Admin/Kitchen)*

#### GET /api/menu/kitchen-capacity *(Admin)*

Get current daily order capacity setting.

#### PATCH /api/menu/kitchen-capacity *(Admin)*

Set the daily kitchen capacity.

```json
{ "capacity": 150 }
```

---

## 7. Cart

**Prefix:** `/api/cart` | Auth required.

---

### GET /api/cart

Get the authenticated user's cart with live item prices.

**Response 200:**
```json
{
  "items": [
    {
      "id": "uuid",
      "menu_item_id": "uuid",
      "name": "Chicken & Rice",
      "price": 2500,
      "quantity": 2,
      "notes": "No pepper",
      "selected_variations": [{ "group_id": "uuid", "option_id": "uuid", "name": "Coleslaw", "price_delta": 0 }]
    }
  ],
  "subtotal": 5000,
  "item_count": 2
}
```

---

### POST /api/cart

Add an item to the cart. If the item already exists, quantity is incremented.

```json
{
  "menu_item_id": "<uuid>",
  "quantity": 2,
  "notes": "No pepper please",
  "selected_variations": [
    { "group_id": "<uuid>", "option_id": "<uuid>" }
  ]
}
```

---

### PATCH /api/cart/<cart_item_id>

Update quantity or notes. Setting `quantity` to `0` removes the item.

```json
{ "quantity": 3, "notes": "Extra sauce" }
```

---

### DELETE /api/cart/<cart_item_id>

Remove a single item from the cart.

---

### DELETE /api/cart

Clear all items from the cart.

---

## 8. Saved Items

**Prefix:** `/api/saved` | Auth required.

Save items for later (like a wishlist).

---

### GET /api/saved

List saved items.

---

### POST /api/saved

Save an item.

```json
{ "menu_item_id": "<uuid>" }
```

---

### PATCH /api/saved/<item_id>

Update notes on a saved item.

---

### DELETE /api/saved/<item_id>

Remove a saved item.

---

### POST /api/saved/<item_id>/move-to-cart

Move a saved item into the active cart.

---

### POST /api/saved/from-cart/<cart_item_id>

Save a cart item for later (removes from cart, adds to saved).

---

## 9. Orders

**Prefix:** `/api/orders`

---

### POST /api/orders

Create a new order. Supports both **authenticated** and **guest** checkout.

**Auth:** Optional (`Authorization` header optional for guests)

**Body:**
```json
{
  "items": [
    {
      "menu_item_id": "<uuid>",
      "quantity": 2,
      "notes": "Extra sauce",
      "selected_variations": [
        { "group_id": "<uuid>", "option_id": "<uuid>" }
      ],
      "addon_ids": ["<uuid>"]
    }
  ],
  "payment_method": "wallet",
  "delivery_type": "on_campus",
  "delivery_location_id": "<hostel_uuid>",
  "promo_code": "PROMO10",
  "notes": "Call before delivering",
  "is_scheduled": false,
  "scheduled_for_window_id": "<window_uuid>",
  "scheduled_date": "2026-08-10",

  "squad_name": "Block C Crew",

  "guest_name": "Amara Eze",
  "guest_phone": "08012345678",
  "guest_email": "amara@example.com"
}
```

**`payment_method`:** `wallet` | `card` | `split`
> Guests cannot use `wallet` — must use `card`.

**`delivery_type`:** `on_campus` | `off_campus`

**Squad orders:** Include `squad_name` and the item count must be ≥ `SQUAD_ORDER_MIN_ITEMS` (default 3) and ≤ `SQUAD_ORDER_MAX_ITEMS` (default 6).

**Response 201:**
```json
{
  "id": "uuid",
  "order_number": "HG-2026-001",
  "status": "received",
  "total": 5000,
  "items": [...],
  "claim_token": "abc123",
  "paystack_authorization_url": "https://paystack.com/pay/...",
  "delivery_window": { "label": "12:00 PM – 1:00 PM", "date": "2026-08-06" }
}
```

---

### GET /api/orders

List authenticated user's orders.

| Query | Description |
|-------|-------------|
| `status` | Filter by status |
| `limit` | Default 20 |
| `offset` | Default 0 |

---

### GET /api/orders/<order_id>

Get order detail. Authenticated users can only see their own orders.
Guests can access using `?claim_token=<token>`.

---

### PATCH /api/orders/<order_id>/status *(Kitchen/Rider/Admin)*

Update order status. Valid transitions enforced by the state machine.

```json
{ "status": "preparing", "notes": "Estimated 15 minutes" }
```

**Order State Machine:**
```
scheduled → received → preparing → ready → assigned → out_for_delivery
                                                      → delivered
                                                      → delivery_attempted → unclaimed
Any pre-delivery state → cancelled | refunded
```

---

### POST /api/orders/<order_id>/walk

Mark order as "walk-in pickup" (no delivery). Auth required.

---

### POST /api/orders/<order_id>/review

Leave a review for a delivered order. Auth required.

```json
{
  "rating": 5,
  "comment": "Fast delivery, great food!",
  "item_ratings": [{ "menu_item_id": "<uuid>", "rating": 5 }]
}
```

---

### POST /api/orders/<order_id>/claim *(Guest)*

Claim a guest order after registering. Links the order to the new account.

```json
{ "claim_token": "abc123" }
```

---

### POST /api/orders/<order_id>/refund *(Admin)*

Initiate a refund for an order.

```json
{ "reason": "Item out of stock", "refund_to": "wallet" }
```

---

### GET /api/orders/scheduled

Get the authenticated user's scheduled future orders.

---

### DELETE /api/orders/<order_id>/scheduled

Cancel a scheduled order before it's received.

---

### GET /api/orders/active

Get currently active (in-progress) orders for the authenticated user.

---

### GET /api/orders/delivery-windows

List available delivery windows for ordering.

**Response 200:**
```json
[
  {
    "id": "uuid",
    "label": "12:00 PM – 1:00 PM",
    "date": "2026-08-06",
    "is_open": true,
    "available_slots": 40
  }
]
```

---

### GET /api/orders/delivery-windows/status

Check if ordering is currently open or closed.

**Response 200:**
```json
{ "is_open": true, "next_window": "12:00 PM – 1:00 PM", "reason": null }
```

---

### GET /api/orders/delivery-zones

List delivery zones (on-campus vs off-campus areas).

---

### POST /api/orders/validate-promo

Validate a promo code before checkout.

```json
{ "promo_code": "PROMO10", "order_total": 5000 }
```

**Response 200:**
```json
{
  "valid": true,
  "discount_type": "percentage",
  "discount_value": 10,
  "discount_amount": 500,
  "final_total": 4500
}
```

---

### POST /api/orders/<order_id>/cancel

Cancel an in-progress order (user).

```json
{ "reason": "Changed my mind" }
```

---

### POST /api/orders/<order_id>/reorder

Reorder a previous order — copies items to cart.

---

### POST /api/orders/<order_id>/share

Generate a shareable link/card for the order. Awards `SOCIAL_SHARE_HP` if configured.

---

### POST /api/orders/<order_id>/squad-members

Add members to a squad order and invite them.

```json
{
  "members": [
    { "name": "Tunde", "email": "tunde@futa.edu.ng", "phone": "08011111111" }
  ]
}
```

---

### GET /api/orders/<order_id>/history

Get the full status transition history for an order.

---

## 10. HP Economy

**Prefix:** `/api/hp`

Holy Points (HP) are the loyalty currency. HP is split into:
- **Active HP:** Spendable immediately
- **Pending HP:** Earned from food orders, unlocked as you spend

---

### GET /api/hp/balance

Get the authenticated user's HP balance.

**Response 200:**
```json
{
  "active_hp": 350,
  "pending_hp": 200,
  "total_visible": 550,
  "tier": "bronze",
  "tier_multiplier": 1.0
}
```

---

### GET /api/hp/transactions

Get HP transaction history.

| Query | Description |
|-------|-------------|
| `type` | Filter: `earn` | `spend` | `unlock` | `expire` |
| `limit` | Default 20 |
| `offset` | Default 0 |

---

### GET /api/hp/tiers

List all HP tiers with thresholds and perks. Public.

**Response 200:**
```json
[
  {
    "slug": "bronze",
    "name": "Bronze",
    "threshold_hp": 0,
    "multiplier": 1.0,
    "perks": ["Base HP earning rate"]
  },
  {
    "slug": "silver",
    "name": "Silver",
    "threshold_hp": 500,
    "multiplier": 1.25,
    "perks": ["1.25× HP earn rate", "Priority order processing"]
  }
]
```

---

### GET /api/hp/unlock-history

Get HP unlock history (HP converted from pending to active on food spend).

---

### GET /api/hp/bundles

List available HP bundle tiers for purchase. Public.

**Response 200:**
```json
[
  { "hp": 100, "label": "Starter Pack", "price_naira": 500 },
  { "hp": 500, "label": "Power Pack", "price_naira": 2500 }
]
```

---

### POST /api/hp/bundles/purchase

Purchase an HP bundle using a Paystack card reference.

```json
{
  "bundle_hp": 500,
  "paystack_reference": "pay_abc123"
}
```

---

The regular HP spin and daily free spin have been retired. There is no
`/api/hp/spin` endpoint.

---

### POST /api/hp/flash-redeem/<reward_id>

Redeem a reward at the flash-sale price (50% HP discount, limited slots, 24h window).

---

### POST /api/hp/transfer *(Auth required)*

Transfer active HP to another user.

```json
{
  "recipient_id": "<uuid>",
  "amount": 100,
  "note": "Treat yourself!"
}
```

> Requires `hp_transfer` feature flag to be enabled and minimum 3 completed orders.

---

### POST /api/hp/admin/grant *(Admin)*

Manually grant HP to a user.

```json
{
  "user_id": "<uuid>",
  "amount": 200,
  "source_type": "admin_grant",
  "notes": "Compensation for delivery delay"
}
```

---

### POST /api/hp/admin/expire *(Admin)*

Manually expire HP for a user.

```json
{ "user_id": "<uuid>", "amount": 100, "reason": "Policy violation" }
```

---

### POST /api/admin/hp/bulk-grant *(Admin)*

Grant HP to multiple users in one call.

```json
{
  "user_ids": ["uuid1", "uuid2"],
  "amount": 50,
  "notes": "Community event bonus"
}
```

---

## 11. Wallet

**Prefix:** `/api/wallet` | Auth required.

---

### GET /api/wallet

Get wallet balance and virtual account information.

**Response 200:**
```json
{
  "balance": 15000,
  "currency": "NGN",
  "virtual_account": {
    "bank_name": "Wema Bank",
    "account_number": "0123456789",
    "account_name": "Holy Grills / Jane Doe"
  }
}
```

---

### POST /api/wallet/fund/card

Initialize a Paystack card payment to top up the wallet.

```json
{ "amount": 5000 }
```

**Response 200:**
```json
{
  "authorization_url": "https://checkout.paystack.com/...",
  "reference": "HG-WALLET-abc123"
}
```

> After payment, Paystack sends a webhook to `POST /api/webhooks/paystack` which credits the wallet automatically.

---

### POST /api/wallet/fund/bank

Provision a Paystack Dedicated Virtual Account for bank transfers. Idempotent — returns the existing account if already provisioned.

**Response 200:**
```json
{
  "bank_name": "Wema Bank",
  "account_number": "0123456789",
  "account_name": "Holy Grills / Jane Doe"
}
```

---

### GET /api/wallet/transactions

Get wallet transaction history.

| Query | Description |
|-------|-------------|
| `type` | `topup` | `order_payment` | `refund` | `withdrawal` | `bank_transfer` |
| `limit` | Default 20 |

---

### GET /api/wallet/admin/transactions *(Admin)*

List all wallet transactions across all users.

---

## 12. Rewards

**Prefix:** `/api/rewards`

---

### GET /api/rewards

List active rewards. Public (no auth required).

| Query | Description |
|-------|-------------|
| `category` | Filter by category |
| `tier` | Filter by minimum tier required |

---

### GET /api/rewards/<reward_id>

Get reward detail.

---

### POST /api/rewards/<reward_id>/redeem *(Auth required)*

Redeem a reward using HP.

```json
{ "quantity": 1 }
```

**Response 200:**
```json
{
  "redemption_id": "uuid",
  "reward_name": "Free Gizzard Wrap",
  "hp_spent": 300,
  "remaining_hp": 150,
  "fulfilment_note": "Our team will fulfil this within 24 hours."
}
```

**Errors:** `400` insufficient HP | tier too low | reward sold out

---

### GET /api/rewards/redemptions *(Auth required)*

Get the authenticated user's redemption history.

---

### GET /api/rewards/admin/redemptions *(Admin)*

List all redemptions across all users.

| Query | Description |
|-------|-------------|
| `status` | `pending` | `fulfilled` | `rejected` |

---

### PATCH /api/rewards/admin/redemptions/<redemption_id> *(Admin)*

Fulfil or reject a redemption.

```json
{ "status": "fulfilled", "admin_note": "Delivered at door" }
```

---

### POST /api/rewards *(Admin)*

Create a new reward.

```json
{
  "name": "Free Gizzard Wrap",
  "description": "A free gizzard wrap on your next order",
  "hp_cost": 300,
  "category": "food",
  "quantity_available": 50,
  "min_tier": "bronze",
  "is_active": true,
  "flash_hp_cost": 150,
  "flash_ends_at": "2026-08-10T23:59:59Z"
}
```

---

### PATCH /api/rewards/<reward_id> *(Admin)*

Update a reward.

---

### DELETE /api/rewards/<reward_id> *(Admin)*

Soft-deactivate a reward (hides it from listings).

---

## 13. Marketplace

**Prefix:** `/api/marketplace`

> Controlled by `marketplace_general` feature flag — must be enabled before students can access.

---

### GET /api/marketplace

List active marketplace listings. Auth required.

---

### GET /api/marketplace/<listing_id>

Get a listing's detail.

---

### POST /api/marketplace/<listing_id>/purchase *(Auth required)*

Purchase a listing.

```json
{ "payment_method": "wallet" }
```

**Response 200:**
```json
{
  "purchase_id": "uuid",
  "listing_name": "Netflix Subscription",
  "code": "NETFL-ABC123",
  "amount_paid": 3500,
  "hp_earned": 50
}
```

---

### GET /api/marketplace/purchases *(Auth required)*

Get the authenticated user's purchase history.

---

### GET /api/marketplace/admin/listings *(Admin)*

List all marketplace listings (including inactive).

---

### GET /api/marketplace/admin/listings/<listing_id> *(Admin)*

Get full listing detail including code inventory count.

---

### POST /api/marketplace/admin/listings *(Admin)*

Create a new listing.

```json
{
  "title": "Netflix 1-Month Subscription",
  "description": "Access to Netflix standard plan",
  "price_naira": 3500,
  "price_hp": 0,
  "vendor_name": "Netflix",
  "category": "streaming",
  "is_active": true
}
```

---

### PATCH /api/marketplace/admin/listings/<listing_id> *(Admin)*

Update a listing.

---

### DELETE /api/marketplace/admin/listings/<listing_id> *(Admin)*

Deactivate a listing.

---

### POST /api/marketplace/admin/codes/<listing_id> *(Admin)*

Upload access codes for a listing (batch).

```json
{
  "codes": ["CODE001", "CODE002", "CODE003"]
}
```

---

### POST /api/marketplace/requests *(Auth required)*

Submit a vendor listing request.

```json
{
  "vendor_name": "Spotify",
  "service_title": "Spotify Premium",
  "description": "Monthly premium plan",
  "suggested_price": 2500
}
```

---

### GET /api/marketplace/admin/requests *(Admin)*

List all vendor listing requests.

---

### PATCH /api/marketplace/admin/requests/<request_id> *(Admin)*

Approve or reject a vendor request.

```json
{ "status": "approved", "notes": "Will be added next week" }
```

---

### GET /api/marketplace/admin/purchases *(Admin)*

List all purchases across all users.

---

### PATCH /api/marketplace/admin/purchases/<purchase_id> *(Admin)*

Update a purchase record (e.g., mark code as delivered).

---

## 14. Events

**Prefix:** `/api/events`

---

### GET /api/events

List published events. Public.

| Query | Description |
|-------|-------------|
| `upcoming` | `true` to only show future events |
| `featured` | `true` to only show featured |

---

### GET /api/events/<event_id>

Get event detail including ticket tiers if enabled.

---

### POST /api/events *(Admin)*

Create a new event.

```json
{
  "title": "Freshers Party 2026",
  "description": "Annual FUTA freshers bash",
  "location": "FUTA Main Auditorium",
  "starts_at": "2026-09-01T18:00:00Z",
  "ends_at": "2026-09-01T22:00:00Z",
  "capacity": 500,
  "is_paid": true,
  "hp_reward": 40,
  "hp_per_attendee": 40,
  "is_published": true,
  "is_featured": false
}
```

---

### GET /api/events/admin *(Admin)*

List all events (including unpublished).

---

### PATCH /api/events/<event_id> *(Admin)*

Update event details.

---

### DELETE /api/events/<event_id> *(Admin)*

Delete an event. Cascades to tickets and check-ins.

---

### POST /api/events/<event_id>/qr *(Admin)*

Generate/regenerate the QR check-in token for an event.

**Response 200:**
```json
{
  "qr_token": "HG-EVT-abc123xyz",
  "qr_url": "https://api.holygrills.ng/events/uuid/checkin?token=HG-EVT-abc123xyz"
}
```

---

### POST /api/events/<event_id>/register *(Auth required)*

Register for an event.

```json
{
  "tier_id": "<tier_uuid>",
  "payment_method": "wallet"
}
```

> If the event has no tiers, `tier_id` is optional.
> Payment methods: `wallet` | `hp` (if HP-priced tier)

**Response 201:**
```json
{
  "ticket_id": "uuid",
  "event_title": "Freshers Party 2026",
  "tier_name": "VIP",
  "qr_code": "HG-TKT-abc123",
  "hp_earned": 40,
  "status": "confirmed"
}
```

---

### POST /api/events/<event_id>/checkin

Check in to an event using the QR code token. Auth required.

```json
{ "qr_token": "HG-EVT-abc123xyz" }
```

**Response 200:**
```json
{
  "message": "Check-in successful",
  "event_title": "Freshers Party 2026",
  "hp_awarded": 40,
  "checked_in_at": "2026-09-01T18:15:00Z"
}
```

---

### Ticket Tiers

#### GET /api/events/<event_id>/tiers

List ticket tiers for an event. Public.

**Response 200:**
```json
[
  {
    "id": "uuid",
    "name": "VIP",
    "price_naira": 5000,
    "price_hp": 0,
    "capacity": 30,
    "sold_count": 12,
    "description": "VIP access with reserved seating"
  },
  {
    "id": "uuid",
    "name": "Regular",
    "price_naira": 2000,
    "price_hp": 0,
    "capacity": 200,
    "sold_count": 45,
    "description": null
  }
]
```

#### POST /api/events/<event_id>/tiers *(Admin)*

Create a ticket tier.

```json
{
  "name": "VIP",
  "price_naira": 5000,
  "price_hp": 0,
  "capacity": 30,
  "description": "VIP access with reserved seating"
}
```

#### PATCH /api/events/tiers/<tier_id> *(Admin)*

Update a ticket tier.

```json
{ "price_naira": 5500, "capacity": 35 }
```

#### DELETE /api/events/tiers/<tier_id> *(Admin)*

Delete a tier. Returns `400` if tickets have already been sold for this tier.

---

### Event Registrant Management *(Admin)*

#### GET /api/events/<event_id>/registrants *(Admin)*

List all registrants for an event. Supports `?format=csv` for CSV download.

| Query | Description |
|-------|-------------|
| `format` | `json` (default) or `csv` |
| `tier_id` | Filter by tier |
| `checked_in` | `true` / `false` |

**Response 200 (JSON):**
```json
[
  {
    "ticket_id": "uuid",
    "user_id": "uuid",
    "full_name": "Jane Doe",
    "email": "jane@futa.edu.ng",
    "phone": "08012345678",
    "tier_name": "VIP",
    "status": "confirmed",
    "checked_in_at": null
  }
]
```

**Response 200 (CSV):** `Content-Type: text/csv` — downloadable file.

#### POST /api/events/<event_id>/send-registrants-to-host *(Admin)*

Email the full registrant list as an HTML table to the event host.

```json
{
  "host_email": "organizer@company.com",
  "host_name": "Event Organizer"
}
```

**Response 200:**
```json
{ "message": "Registrant list sent", "host_email": "...", "count": 65 }
```

---

### Catering Requests

#### GET /api/events/catering-requests *(Admin)*

List all catering requests.

#### POST /api/events/catering-requests

Submit a catering request. Auth required.

```json
{
  "event_name": "Departmental Dinner",
  "event_date": "2026-09-15",
  "location": "Engineering Hall",
  "expected_attendees": 100,
  "menu_notes": "No seafood",
  "contact_name": "Tunde Adeyemi",
  "contact_phone": "08011112222"
}
```

#### PATCH /api/events/catering-requests/<request_id> *(Admin)*

Update a catering request status.

```json
{ "status": "approved", "notes": "Confirmed. Budget ₦150,000." }
```

---

## 15. Referrals

**Prefix:** `/api/referrals` | Auth required.

---

### GET /api/referrals

Get the authenticated user's referrals list.

**Response 200:**
```json
{
  "referrals": [
    { "referee_name": "Tunde", "status": "completed", "hp_earned": 75, "completed_at": "2026-07-15" }
  ],
  "total_referrals": 1,
  "referral_code": "JANE123"
}
```

---

### GET /api/referrals/stats

Get referral stats and milestone progress.

**Response 200:**
```json
{
  "total_referrals": 4,
  "completed_referrals": 3,
  "total_hp_earned": 225,
  "next_milestone": { "count": 5, "bonus_hp": 150 },
  "milestones_reached": []
}
```

---

### POST /api/referrals/complete

Internal endpoint to mark a referral as complete (called after first order delivery).

---

## 16. Notifications

**Prefix:** `/api/notifications` | `/api/push` | Auth required.

---

### POST /api/push/subscribe

Register a push subscription (Expo / Web Push).

```json
{
  "subscription": {
    "endpoint": "https://fcm.googleapis.com/...",
    "keys": { "p256dh": "...", "auth": "..." }
  },
  "platform": "web"
}
```

---

### DELETE /api/push/subscribe

Unsubscribe from push notifications.

---

### GET /api/notifications

List the authenticated user's notifications (in-app).

| Query | Description |
|-------|-------------|
| `unread_only` | `true` to filter unread |
| `limit` | Default 20 |

---

### POST /api/notifications/<notification_id>/read

Mark a notification as read.

---

### POST /api/notifications/read-all

Mark all notifications as read.

---

### GET /api/notifications/preferences

Get the authenticated user's notification preferences.

---

### PATCH /api/notifications/preferences

Update notification preferences.

```json
{
  "push_enabled": true,
  "email_enabled": true,
  "marketing_enabled": false
}
```

---

### GET /api/notifications/blasts *(Admin)*

List all notification blasts sent.

---

### GET /api/notifications/blasts/<blast_id> *(Admin)*

Get detail of a specific blast.

---

### POST /api/notifications/blasts *(Admin)*

Send a push + in-app notification blast to all users or a segment.

```json
{
  "title": "🎉 Flash Sale Alert!",
  "body": "20% off all combos for the next 2 hours. Order now!",
  "segment": "all",
  "data": { "screen": "menu" }
}
```

> `segment` options: `all` | `active_users` | `tier:silver` | `tier:gold`

---

## 17. Admin Panel

**Prefix:** `/api/admin` | Admin role required for all endpoints.

---

### Users

#### GET /api/admin/users

List all users with filters.

| Query | Description |
|-------|-------------|
| `role` | `student` | `admin` | `kitchen` | `rider` |
| `tier` | `bronze` | `silver` | `gold` | `platinum` |
| `search` | Name or email search |
| `is_active` | `true` / `false` |

#### GET /api/admin/users/<user_id>

Get full user profile including HP balance, wallet balance, tier.

#### GET /api/admin/users/<user_id>/orders

Get all orders for a specific user.

#### GET /api/admin/users/<user_id>/hp

Get HP transaction history for a specific user.

#### GET /api/admin/users/<user_id>/wallet

Get wallet transaction history for a specific user.

#### PATCH /api/admin/users/<user_id>/role

Change a user's role.

```json
{ "role": "kitchen" }
```

Valid roles: `student` | `kitchen` | `rider` | `admin`

#### POST /api/admin/users/<user_id>/deactivate

Deactivate a user account (blocks login).

#### POST /api/admin/users/<user_id>/activate

Reactivate a deactivated user account.

---

### Orders

#### GET /api/admin/orders

List all orders with filters.

| Query | Description |
|-------|-------------|
| `status` | Filter by order status |
| `date` | `YYYY-MM-DD` |
| `search` | Order number or user name |
| `limit` | Default 50 |

---

### Promo Codes

#### GET /api/admin/promo-codes

List all promo codes.

#### POST /api/admin/promo-codes

Create a new promo code.

```json
{
  "code": "PROMO10",
  "discount_type": "percentage",
  "discount_value": 10,
  "max_uses": 100,
  "min_order_value": 2000,
  "expires_at": "2026-12-31T23:59:59Z",
  "is_active": true
}
```

`discount_type`: `percentage` | `fixed`

#### PATCH /api/admin/promo-codes/<promo_id>

Update a promo code.

#### GET /api/admin/promo-codes/<promo_id>/uses

Get usage history for a promo code.

---

### Delivery Windows

#### GET /api/admin/delivery-windows

List all delivery windows.

#### POST /api/admin/delivery-windows

Create a new delivery window.

```json
{
  "label": "12:00 PM – 1:00 PM",
  "date": "2026-08-06",
  "open_time": "11:30",
  "close_time": "13:00",
  "capacity": 80
}
```

#### POST /api/admin/delivery-windows/<window_id>/close

Manually close a delivery window (stops accepting new orders).

#### POST /api/admin/delivery-windows/<window_id>/reopen

Reopen a closed delivery window.

---

### Delivery Batches

#### GET /api/admin/delivery-batches

List all delivery batches.

#### GET /api/admin/delivery-batches/<batch_id>

Get batch detail.

#### POST /api/admin/delivery-batches

Create a new delivery batch.

```json
{
  "window_id": "<uuid>",
  "rider_id": "<uuid>",
  "zone": "Main Campus North"
}
```

#### PATCH /api/admin/delivery-batches/<batch_id>

Update a batch (assign rider, change zone, update status).

#### DELETE /api/admin/delivery-batches/<batch_id>

Cancel a batch.

#### GET /api/admin/delivery-batches/<batch_id>/orders

List all orders in a batch.

---

### Abandoned Carts

#### GET /api/admin/abandoned-carts

List abandoned carts (carts with items not ordered after 60 minutes).

#### POST /api/admin/abandoned-carts/<cart_id>/nudge

Send a recovery push + in-app notification to the user.

---

### Audit Log

#### GET /api/admin/audit-log

Get admin action audit log.

| Query | Description |
|-------|-------------|
| `actor_id` | Filter by admin who performed action |
| `entity_type` | e.g. `menu_items` |
| `action` | `create` | `update` | `delete` |

---

### Cron Jobs (Manual Trigger)

#### POST /api/admin/cron/<job_name>

Manually trigger a scheduled background job.

**Available jobs:**

| Job Name | Description |
|----------|-------------|
| `birthday_hp` | Award birthday HP to today's birthdays |
| `leaderboard_reset` | Reset monthly leaderboard and assign prizes |
| `hp_expiry` | Run HP expiry/decay for inactive users |
| `winback` | Send win-back notifications to inactive users |
| `abandoned_cart` | Send nudges for abandoned carts |
| `tier_recalculation` | Recalculate tiers for all users |
| `streak_reset` | Reset daily streak counts |

#### GET /api/admin/cron/status

Get last run time and status for all cron jobs.

---

## 18. Kitchen

**Prefix:** `/api/kitchen` | Kitchen or Admin role required.

---

### GET /api/kitchen/settings

Get all kitchen settings.

---

### GET /api/kitchen/settings/<key>

Get a specific kitchen setting by key (e.g., `daily_order_capacity`).

---

### PATCH /api/kitchen/settings *(Kitchen/Admin)*

Update kitchen settings.

```json
{
  "daily_order_capacity": 120,
  "prep_time_minutes": 20
}
```

---

### GET /api/kitchen/queue

Get the live order queue grouped by status.

**Response 200:**
```json
{
  "received": [ { "id": "uuid", "order_number": "HG-001", "items": [...], "created_at": "..." } ],
  "preparing": [ ... ],
  "ready": [ ... ]
}
```

---

### GET /api/kitchen/windows

Get today's delivery windows with order counts.

---

### GET /api/kitchen/scheduled

Get upcoming scheduled orders.

---

### GET /api/kitchen/metrics

Get kitchen performance metrics (avg prep time, orders by status, throughput).

---

### GET /api/kitchen/batch-summary/<window_id>

Get an order summary for a specific delivery window (for batch preparation).

---

### POST /api/kitchen/batch/<batch_id>/advance

Advance a batch order to the next status in the queue.

---

## 19. Riders

**Prefix:** `/api/riders` | Rider or Admin role required.

---

### GET /api/riders/my-batch

Get the rider's currently assigned delivery batch with all orders.

**Response 200:**
```json
{
  "batch_id": "uuid",
  "zone": "Main Campus North",
  "orders": [
    {
      "id": "uuid",
      "order_number": "HG-001",
      "status": "assigned",
      "delivery_address": { "hostel": "Block C", "room": "14B" },
      "customer_name": "Jane Doe",
      "customer_phone": "08012345678"
    }
  ]
}
```

---

### POST /api/riders/orders/<order_id>/pickup

Mark an order as picked up from kitchen (status → `out_for_delivery`).

---

### POST /api/riders/orders/<order_id>/deliver

Mark an order as delivered (status → `delivered`). Awards HP to customer.

```json
{ "notes": "Left at the gate" }
```

---

### POST /api/riders/orders/<order_id>/attempt

Mark a delivery attempt (status → `delivery_attempted`).

```json
{ "notes": "Customer not available. Will retry." }
```

---

### PATCH /api/riders/availability

Update rider availability status.

```json
{ "is_available": true }
```

---

### GET /api/riders/history

Get the rider's delivery history.

| Query | Description |
|-------|-------------|
| `date` | `YYYY-MM-DD` |
| `limit` | Default 20 |

---

### GET /api/riders/stats

Get rider performance stats (deliveries, avg time, completion rate).

---

### GET /api/riders/earnings

Get rider earnings summary.

---

### GET /api/riders/call/<order_id>

Get the customer's phone number for an order (to call before delivery).

---

## 20. Leaderboard

**Prefix:** `/api/leaderboard`

---

### GET /api/leaderboard

Get the current monthly leaderboard (top HP earners).

| Query | Description |
|-------|-------------|
| `limit` | Default 10, max 50 |
| `offset` | Default 0 |

**Response 200:**
```json
{
  "month": "2026-08",
  "entries": [
    { "rank": 1, "user_id": "uuid", "full_name": "Jane Doe", "hp_earned_month": 2400, "tier": "gold" },
    { "rank": 2, ... }
  ]
}
```

---

### GET /api/leaderboard/my-rank

Get the authenticated user's current rank and HP for this month.

**Response 200:**
```json
{
  "rank": 4,
  "hp_earned_month": 1800,
  "entries_above": 3,
  "prizes_if_maintain": { "free_sides": 0, "exclusive_spins": 1 }
}
```

---

### GET /api/leaderboard/hall-of-fame

Get the Hall of Fame summary (users who have held #1 for 3+ consecutive months).

---

### GET /api/leaderboard/hall-of-fame/inductees

List all Hall of Fame inductees.

---

### GET /api/leaderboard/hall-of-fame/inductees/<user_id>/card

Get the shareable Hall of Fame card data for an inductee.

---

### GET /api/leaderboard/squad

Get the squad leaderboard (groups ordered by combined HP).

---

### GET /api/leaderboard/squad/my-rank

Get the authenticated user's squad rank.

---

### Leaderboard Prizes (Admin)

At the end of each month, the `leaderboard_reset` cron assigns prizes automatically:

| Rank | Free Side Credits | Exclusive Spins |
|------|------------------|-----------------|
| #1 | 3 credits | 1 spin |
| #2 | 2 credits | 1 spin |
| #3 | 1 credit | 1 spin |
| #4–10 | — | 1 spin |

#### GET /api/admin/leaderboard-prizes *(Admin)*

List pending and fulfilled prize records.

| Query | Description |
|-------|-------------|
| `status` | `pending` | `fulfilled` |
| `month` | `YYYY-MM` |

#### PATCH /api/admin/leaderboard-prizes/<record_id> *(Admin)*

Mark a prize as fulfilled.

```json
{ "status": "fulfilled", "notes": "Credits and spins credited on 2026-08-01" }
```

---

### Hall of Fame Rewards (Admin)

#### GET /api/admin/hall-of-fame-rewards *(Admin)*

List all Hall of Fame reward records (reward box preparation).

#### PATCH /api/admin/hall-of-fame-rewards/<record_id> *(Admin)*

Update a Hall of Fame reward status.

```json
{ "status": "box_prepared" }
```

Status values: `pending` | `box_prepared` | `fulfilled` | `cancelled`

---

## 21. Challenges & Badges (retired)

The challenge, milestone, and badge subsystem has been retired. The
`/api/challenges` prefix is no longer registered and existing database
definitions are deactivated by the cleanup migration.

**Response 200:**
```json
{
  "completed_milestones": [...],
  "in_progress": [...],
  "badges": [
    { "name": "Top 10 Finisher", "awarded_at": "2026-08-01", "expires_at": "2026-09-01" }
  ]
}
```

---

### POST /api/challenges/<milestone_id>/complete

Mark a challenge as complete (for manually-completable types). Auth required.

---

### POST /api/challenges/social-follow

Record a social media follow action. Awards HP if configured. Auth required.

```json
{ "platform": "instagram", "action": "follow" }
```

---

### Admin — Challenge Management

#### GET /api/challenges/admin *(Admin)*

List all challenges (including inactive).

#### POST /api/challenges/admin *(Admin)*

Create a new challenge.

```json
{
  "title": "Combo Explorer",
  "description": "Order 3 different combos over 3 weeks",
  "hp_reward": 300,
  "trigger_type": "item_category",
  "trigger_config": { "category": "combos", "distinct_items": 3, "weeks": 3 },
  "is_active": true
}
```

**Supported `trigger_type` values:**

| Type | What it checks |
|------|---------------|
| `order_count` | Total number of orders placed |
| `order_distinct_days_weekly` | Orders on 4+ different weekdays in same week |
| `item_category` | Order N distinct items from a category over N weeks |
| `menu_item_id` | Order a specific item N times |
| `min_order_total` | Place an order ≥ ₦X |
| `referral_count` | Refer N friends |
| `social_follow` | Follow on social media |
| `event_checkin` | Check in to N events |
| `review_count` | Leave N reviews |
| `login_streak` | Maintain login streak for N days |

#### PATCH /api/challenges/admin/<milestone_id> *(Admin)*

Update a challenge.

#### DELETE /api/challenges/admin/<milestone_id> *(Admin)*

Delete a challenge.

#### POST /api/challenges/admin/<milestone_id>/grant *(Admin)*

Manually grant a challenge completion to a specific user.

```json
{ "user_id": "<uuid>", "notes": "Manual award — community event" }
```

---

## 22. Daily Check-In

**Prefix:** `/api/checkin` | Auth required.

The check-in system is **separate from login streak** — users must explicitly tap "Check In" each day.

---

### POST /api/checkin

Record today's check-in. Awards HP if `daily_checkin_hp` is set in system_settings.
Idempotent — returns `200` if already checked in today.

**Response 201 (new check-in):**
```json
{
  "message": "Checked in! +5 HP awarded",
  "checkin_date": "2026-08-06",
  "hp_awarded": 5
}
```

**Response 200 (already done today):**
```json
{
  "message": "Already checked in today",
  "already_checked_in": true
}
```

---

### GET /api/checkin/history

Get check-in history for the authenticated user (for calendar display).

| Query | Description |
|-------|-------------|
| `limit` | Default 30, max 90 |
| `offset` | Default 0 |

**Response 200:**
```json
{
  "checkins": [
    { "checkin_date": "2026-08-06", "created_at": "2026-08-06T08:15:00Z" },
    { "checkin_date": "2026-08-05", "created_at": "2026-08-05T07:45:00Z" }
  ],
  "total": 2,
  "checked_in_today": true
}
```

> Use `checkins[].checkin_date` to render a calendar with ✅ marks on checked-in days.

---

## 23. Free Side Credits

**Prefix:** `/api/free-sides` | Auth required.

Free side credits are awarded to top-3 leaderboard finishers at month end:
- #1 → 3 credits
- #2 → 2 credits  
- #3 → 1 credit

Credits expire 60 days after award and can be redeemed at checkout.

---

### GET /api/free-sides

Check the authenticated user's free side credit balance.

**Response 200:**
```json
{
  "total_credits": 2,
  "credits": [
    {
      "id": "uuid",
      "credits_remaining": 2,
      "source": "leaderboard",
      "month": "2026-07",
      "expires_at": "2026-09-30T23:59:59Z"
    }
  ],
  "available_sides": ["Fries", "Coleslaw", "Plantain", "Gizzard"]
}
```

> **At checkout:** if `total_credits > 0`, show a pop-up prompting the user to select a free side.

---

### POST /api/free-sides/redeem

Redeem one free side credit at checkout.

```json
{
  "side_choice": "Coleslaw",
  "order_id": "<uuid>"
}
```

**Response 200:**
```json
{
  "message": "Free side redeemed!",
  "side_choice": "Coleslaw",
  "credits_remaining": 1,
  "order_id": "<uuid>"
}
```

**Errors:**
- `400` `side_choice` not in available list
- `400` No active credits

> The kitchen order view will show a **🏆 Reward** tag on orders with a redeemed free side.

---

## 24. Exclusive Spin

**Prefix:** `/api/exclusive-spin` | Auth required.

Exclusive spin is awarded to top-10 leaderboard finishers:
- Ranks #1–10 each get 1 free spin per month
- Spins are rewards only and cannot be purchased with HP
- Spins expire 30 days after award

---

### GET /api/exclusive-spin

Check available spin credits.

**Response 200:**
```json
{
  "total_spins": 1,
  "spins": [
    {
      "id": "uuid",
      "spin_count": 1,
      "source": "leaderboard",
      "month": "2026-07",
      "expires_at": "2026-08-31T23:59:59Z"
    }
  ],
  "prizes": [
    { "name": "Free Sausage ×2", "weight": 15 },
    { "name": "Free Gizzard ×3", "weight": 15 },
    { "name": "Free Side", "weight": 10 },
    { "name": "Free Coleslaw", "weight": 10 },
    { "name": "HP Jackpot +750", "weight": 5 },
    { "name": "HP Bolt +300", "weight": 20 },
    { "name": "HP Boost +150", "weight": 15 },
    { "name": "Double HP next order", "weight": 10 }
  ]
}
```

---

### POST /api/exclusive-spin/spin

Consume one spin credit and return the prize result.

**Response 200:**
```json
{
  "prize": "HP Bolt +300",
  "hp_won": 300,
  "new_hp_balance": 650,
  "spins_remaining": 0
}
```

**Errors:**
- `400` No spin credits available

---

## 25. Storefront

**Prefix:** `/api/storefront`

The storefront is the public-facing landing page/app home.

---

### GET /api/storefront/sections

Get all active storefront sections (hero, about, menu preview, etc.). Public.

---

### POST /api/storefront/sections *(Admin)*

Create a new storefront section.

```json
{
  "title": "Today's Specials",
  "content": "...",
  "section_type": "menu_preview",
  "is_active": true,
  "sort_order": 1
}
```

---

### PATCH /api/storefront/sections/<section_id> *(Admin)*

Update a section.

---

### DELETE /api/storefront/sections/<section_id> *(Admin)*

Delete a section.

---

### GET /api/storefront/operating-hours

Get the storefront's operating hours. Public.

---

### PATCH /api/storefront/operating-hours *(Admin)*

Update regular operating hours.

```json
{
  "monday": { "open": "08:00", "close": "17:00" },
  "tuesday": { "open": "08:00", "close": "17:00" }
}
```

---

### POST /api/storefront/operating-hours/override *(Admin)*

Create a one-time operating hours override (e.g., holiday closure).

```json
{
  "date": "2026-08-15",
  "is_closed": true,
  "reason": "Public holiday"
}
```

---

### POST /api/storefront/promo-codes/validate

Validate a promo code (same as `/api/orders/validate-promo` but public-facing).

---

### GET /api/storefront/early-supporters

List early supporter program sections. Public.

---

### POST /api/storefront/early-supporters *(Admin)*

Create an early supporter entry.

---

### PATCH /api/storefront/early-supporters/<section_id> *(Admin)*

Update an early supporter entry.

---

### DELETE /api/storefront/early-supporters/<section_id> *(Admin)*

Delete an early supporter entry.

---

### GET /api/storefront/banners

List active banners (promotional images/announcements). Public.

---

### POST /api/storefront/banners *(Admin)*

Create a banner.

```json
{
  "title": "New Menu Drop!",
  "image_url": "https://...",
  "link_url": "/menu",
  "is_active": true,
  "expires_at": "2026-08-31T23:59:59Z"
}
```

---

### PATCH /api/storefront/banners/<banner_id> *(Admin)*

Update a banner.

---

### DELETE /api/storefront/banners/<banner_id> *(Admin)*

Delete a banner.

---

### POST /api/storefront/newsletter

Subscribe to the newsletter. Public.

```json
{ "email": "student@futa.edu.ng", "name": "Jane Doe" }
```

---

### POST /api/storefront/newsletter/unsubscribe

Unsubscribe from the newsletter.

```json
{ "email": "student@futa.edu.ng" }
```

---

### GET /api/storefront/newsletter *(Admin)*

List all newsletter subscribers.

---

## 26. Analytics

**Prefix:** `/api/analytics` | Admin role required.

All analytics endpoints support `?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` for date filtering.

---

### GET /api/analytics/dashboard

High-level dashboard summary: total orders, revenue, active users, HP issued, top items.

---

### GET /api/analytics/sales

Sales analytics: daily/weekly/monthly revenue breakdown.

---

### GET /api/analytics/hp

HP economy analytics: HP issued, spent, expired, active balance totals.

---

### GET /api/analytics/referrals

Referral analytics: total referrals, completion rate, HP awarded.

---

### GET /api/analytics/orders

Order analytics: orders by status, by delivery type, avg order value.

---

### GET /api/analytics/items

Menu item performance: most ordered, revenue per item, sell-out frequency.

---

### GET /api/analytics/users

User analytics: registrations, active users, tier distribution, churn.

---

### GET /api/analytics/retention

Cohort retention analytics.

---

### GET /api/analytics/marketplace

Marketplace analytics: purchases, revenue, top listings.

---

### GET /api/analytics/gifts

First-order gift analytics: gifts issued, cost, conversion rates.

---

### GET /api/analytics/abandoned-carts

Abandoned cart analytics: count, recovery rate, nudge effectiveness.

---

### GET /api/analytics/export

Export analytics data as CSV.

| Query | Description |
|-------|-------------|
| `type` | `orders` | `users` | `hp` | `sales` |
| `start_date` | `YYYY-MM-DD` |
| `end_date` | `YYYY-MM-DD` |

---

## 27. Order Locks

**Prefix:** `/api/order-locks` | Auth required.

Order locks allow users to "pre-book" a meal slot with a deposit. Useful for recurring orders.

---

### POST /api/order-locks

Create an order lock.

```json
{
  "menu_item_id": "<uuid>",
  "quantity": 1,
  "delivery_window_id": "<uuid>",
  "notes": "Same as last time"
}
```

---

### GET /api/order-locks

List the authenticated user's order locks.

---

### GET /api/order-locks/<lock_id>

Get a specific order lock detail.

---

### PATCH /api/order-locks/<lock_id>/reschedule

Reschedule an order lock to a different window.

```json
{ "delivery_window_id": "<uuid>" }
```

---

### DELETE /api/order-locks/<lock_id>

Cancel an order lock.

---

### GET /api/order-locks/admin/all *(Admin)*

List all order locks across all users.

---

## 28. Delivery Locations

**Prefix:** `/api/delivery`

---

### GET /api/delivery/hostels

List all on-campus hostel delivery locations. Public.

**Response 200:**
```json
[
  { "id": "uuid", "name": "Block C", "zone": "North Campus", "delivery_fee": 100 }
]
```

---

### GET /api/delivery/gates

List all off-campus gate delivery points. Public.

---

### POST /api/delivery/calculate-fee

Calculate the delivery fee for a specific location.

```json
{
  "delivery_type": "on_campus",
  "delivery_location_id": "<hostel_uuid>"
}
```

**Response 200:**
```json
{ "fee": 100, "estimated_time_minutes": 20 }
```

---

### Delivery Admin *(Admin)*

#### GET /api/delivery/admin/hostels

List all hostels (including inactive).

#### POST /api/delivery/admin/hostels

Create a hostel delivery location.

```json
{
  "name": "Block C",
  "zone": "North Campus",
  "delivery_fee": 100,
  "is_active": true
}
```

#### PATCH /api/delivery/admin/hostels/<hostel_id>

Update a hostel.

#### DELETE /api/delivery/admin/hostels/<hostel_id>

Deactivate a hostel.

#### GET /api/delivery/admin/gates

List all gate locations.

#### POST /api/delivery/admin/gates

Create a gate delivery location.

#### PATCH /api/delivery/admin/gates/<gate_id>

Update a gate.

#### DELETE /api/delivery/admin/gates/<gate_id>

Deactivate a gate.

---

## 29. Graduation

**Prefix:** `/api/graduation` | Auth required.

---

### POST /api/graduation/claim

Claim the one-time graduation HP bonus.

```json
{
  "graduation_year": 2026,
  "department": "Computer Science",
  "evidence_url": "https://..."
}
```

**Response 200:**
```json
{
  "message": "Graduation bonus claimed!",
  "hp_awarded": 1000,
  "new_hp_balance": 1450
}
```

---

## 30. Departments

**Prefix:** `/api/departments`

---

### GET /api/departments

List all active departments. Public.

---

### GET /api/departments/faculties

List departments grouped by faculty. Public.

---

### GET /api/departments/<dept_id>

Get a department by ID. Public.

---

### Department Admin *(Admin)*

#### GET /api/admin/departments

List all departments (including inactive).

#### POST /api/admin/departments

Create a new department.

```json
{
  "name": "Computer Science",
  "faculty": "Engineering",
  "code": "CSC"
}
```

#### PATCH /api/admin/departments/<dept_id>

Update a department.

#### DELETE /api/admin/departments/<dept_id>

Soft-delete (deactivate) a department.

#### POST /api/admin/departments/<dept_id>/restore

Restore a deactivated department.

---

## 31. Academic Levels

**Prefix:** `/api/academic-levels`

---

### GET /api/academic-levels

List all active academic levels (100L, 200L, etc.). Public.

---

### GET /api/academic-levels/<level_id>

Get an academic level by ID. Public.

---

### Academic Level Admin *(Admin)*

#### GET /api/admin/academic-levels

List all academic levels (including inactive).

#### POST /api/admin/academic-levels

Create a new academic level.

```json
{ "name": "100 Level", "code": "100L", "sort_order": 1 }
```

#### PATCH /api/admin/academic-levels/<level_id>

Update an academic level.

#### DELETE /api/admin/academic-levels/<level_id>

Soft-delete an academic level.

#### POST /api/admin/academic-levels/<level_id>/restore

Restore a deactivated academic level.

---

## 32. Admin Gifts & System Settings

**Prefix:** `/api/admin` | Admin role required.

---

### First-Order Gifts

First-order gifts are automatically given to users placing their very first order (if `FIRST_ORDER_GIFT_ENABLED=true`).

#### GET /api/admin/first-order-gifts

List pending and fulfilled first-order gifts.

| Query | Description |
|-------|-------------|
| `status` | `pending` | `fulfilled` |

#### PATCH /api/admin/first-order-gifts/<gift_id>

Mark a gift as fulfilled or update its status.

```json
{ "status": "fulfilled", "notes": "Hot dog included in order bag" }
```

---

### System Settings

Global runtime configuration — no code deploy required to change these values.

#### GET /api/admin/settings

List all system settings as key-value pairs.

**Response 200:**
```json
[
  { "key": "daily_checkin_hp", "value": 5, "description": "HP awarded per daily check-in" },
  { "key": "free_side_options", "value": ["Fries", "Coleslaw", "Plantain", "Gizzard"] },
  { "key": "hp_multiplier", "value": 1.0 },
  { "key": "exclusive_spin_template_items", "value": [...] }
]
```

#### POST /api/admin/settings

Create a new system setting.

```json
{
  "key": "daily_checkin_hp",
  "value": 10,
  "description": "HP awarded for daily check-in"
}
```

#### PATCH /api/admin/settings/<key>

Update a system setting value.

```json
{ "value": 10 }
```

**Commonly configured settings:**

| Key | Type | Purpose |
|-----|------|---------|
| `daily_checkin_hp` | integer | HP per daily check-in |
| `free_side_options` | JSON array | Available free side choices |
| `exclusive_spin_template_items` | JSON array | Spin wheel prizes with weights |
| `hp_multiplier` | float | Global HP earn multiplier |
| `ordering_window_open` | string | Override ordering open time (HH:MM) |
| `ordering_window_close` | string | Override ordering close time (HH:MM) |
| `notification_gap_minutes` | integer | Min minutes between same-type notifications |
| `notification_daily_cap` | integer | Max non-critical notifications per user/day |

---

## 33. Webhooks

**Prefix:** `/api/webhooks`

> **Never call these manually.** These endpoints are called by Paystack/Flutterwave only.
> Verify HMAC signature is done automatically by the backend.

---

### POST /api/webhooks/paystack

Handles Paystack payment events:
- `charge.success` → credits wallet, updates order to `paid`
- `transfer.success` → marks withdrawal as complete
- `dedicatedaccount.assign` → stores virtual account details

---

### POST /api/webhooks/flutterwave

Handles Flutterwave payment events (same logic as Paystack).

---

## 34. Health Check

### GET /api/health

Public health check — no auth required.

**Response 200:**
```json
{
  "api": "Holy Grills",
  "version": "1.0.0",
  "status": "ok",
  "checks": {
    "supabase": "connected",
    "redis": "connected"
  }
}
```

**Response 503 (degraded):**
```json
{
  "status": "degraded",
  "checks": {
    "supabase": "connected",
    "redis": "error: Connection refused"
  }
}
```

> Redis being unavailable is non-fatal (only Celery background jobs are affected). Supabase unavailable is critical.

---

## 35. User Flow Guides

---

### 35a. Guest Order Flow

**Scenario:** A first-time visitor wants to order food without creating an account.

> **Important:** The menu must be publicly accessible (no auth gate) for guest orders to work. Lock only checkout behind auth, not the menu listing.

```
1. BROWSE MENU (no auth)
   GET /api/menu/categories
   GET /api/menu/items?available_only=true
   GET /api/menu/items/<id>   ← shows variation groups + options

2. CHECK DELIVERY OPTIONS (no auth)
   GET /api/delivery/hostels
   GET /api/delivery/gates
   POST /api/delivery/calculate-fee   ← show delivery fee before checkout

3. VALIDATE PROMO (optional, no auth)
   POST /api/orders/validate-promo

4. PLACE ORDER (no auth — guest fields required)
   POST /api/orders
   {
     "items": [...],
     "payment_method": "card",        ← wallet not available to guests
     "delivery_type": "on_campus",
     "delivery_location_id": "<hostel_id>",
     "guest_name": "Amara",
     "guest_phone": "08012345678",
     "guest_email": "amara@example.com"
   }
   ← Response includes: order_id, claim_token, paystack_authorization_url

5. PAYMENT (redirect to Paystack)
   ← Redirect guest to paystack_authorization_url
   ← Paystack webhook fires → order status → "paid" → "received"

6. TRACK ORDER (no auth — use claim_token)
   GET /api/orders/<order_id>?claim_token=abc123

7. REGISTER & CLAIM ORDER (optional — converts guest to member)
   POST /api/auth/register   ← creates account
   POST /api/orders/<order_id>/claim   { "claim_token": "abc123" }
   ← Order is now linked to the new account
   ← First-order HP bonus may be awarded on delivery
```

---

### 35b. Authenticated Student Flow — Full A-Z

```
1. REGISTER / LOGIN
   POST /api/auth/register  OR  POST /api/auth/login
   ← Save access_token + refresh_token

2. COMPLETE PROFILE (optional but recommended)
   PATCH /api/auth/profile
   POST /api/auth/addresses   ← save hostel address
   POST /api/auth/device-token   ← register for push notifications

3. DAILY CHECK-IN (each day)
   POST /api/checkin
   ← Awards 5 HP (configurable)
   GET /api/checkin/history   ← render calendar with ✅ marks

4. BROWSE MENU
   GET /api/menu/categories
   GET /api/menu/items
   GET /api/menu/items/<id>   ← includes variation_groups

5. MANAGE CART
   POST /api/cart   ← add items with selected_variations
   GET /api/cart    ← review cart
   PATCH /api/cart/<id>   ← update quantity
   DELETE /api/cart/<id>  ← remove item

6. CHECKOUT
   GET /api/delivery/hostels   ← pick delivery location
   POST /api/delivery/calculate-fee   ← show fee
   GET /api/hp/balance   ← show HP balance for HP discount

   [If user has free side credits]
   GET /api/free-sides   ← check credits
   → Show pop-up: "You have 2 free side credits! Choose a free side:"
   POST /api/free-sides/redeem   ← redeem before/at order creation

   POST /api/orders
   {
     "items": [...],
     "payment_method": "wallet",   ← or "card", "split"
     "delivery_type": "on_campus",
     "delivery_location_id": "<hostel_uuid>"
   }

7. TRACK ORDER
   GET /api/orders/active   ← polling for live status
   GET /api/orders/<id>
   GET /api/orders/<id>/history   ← full status timeline

8. POST-ORDER ACTIONS
   POST /api/orders/<id>/review   ← leave rating
   GET /api/hp/balance   ← see HP earned
   GET /api/hp/unlock-history   ← see pending→active conversions

9. REWARDS & SPENDING
   GET /api/rewards   ← browse reward catalog
   GET /api/hp/balance   ← check balance
   POST /api/rewards/<id>/redeem   ← redeem with HP
   POST /api/hp/flash-redeem/<id>   ← flash sale redemption

10. LEADERBOARD & SPIN
    GET /api/leaderboard   ← view rankings
    GET /api/leaderboard/my-rank   ← see own position
    GET /api/exclusive-spin   ← check spin credits (if top 10)
    POST /api/exclusive-spin/spin   ← use spin credit

11. REFERRALS
    GET /api/auth/me   ← get referral_code
    GET /api/referrals/stats   ← track progress
    GET /api/referrals   ← list completed referrals

12. CHALLENGES
    GET /api/challenges   ← view active challenges
    GET /api/challenges/my   ← track progress & badges
    POST /api/challenges/<id>/complete   ← complete manual challenges

13. EVENTS
    GET /api/events   ← browse events
    GET /api/events/<id>/tiers   ← view ticket tiers
    POST /api/events/<id>/register   ← register + pay
    POST /api/events/<id>/checkin   ← QR check-in at door

14. WALLET MANAGEMENT
    GET /api/wallet   ← balance + virtual account
    POST /api/wallet/fund/card   ← top up with card
    POST /api/wallet/fund/bank   ← get bank transfer details
    GET /api/wallet/transactions   ← transaction history

15. TOKEN REFRESH (automatic)
    POST /api/auth/refresh   ← on every 401 response
```

---

### 35c. Admin Flow — Complete A-Z

```
1. LOGIN as admin
   POST /api/auth/login   { "email": "admin@holygrills.ng", "password": "..." }

2. MENU MANAGEMENT
   # Categories
   POST /api/menu/categories   ← create category
   PATCH /api/menu/categories/<id>   ← update
   DELETE /api/menu/categories/<id>   ← deactivate

   # Items
   POST /api/menu/items   ← create item
   PATCH /api/menu/items/<id>   ← update price/availability
   POST /api/menu/items/<id>/archive   ← archive

   # Variations (e.g., "Choose your side")
   POST /api/menu/items/<id>/variation-groups   ← create group
   POST /api/menu/items/<id>/variation-groups/<gid>/options   ← add options
   DELETE /api/menu/items/<id>/variation-groups/<gid>   ← remove group

   # Daily capacity
   PATCH /api/menu/kitchen-capacity   { "capacity": 120 }

3. ORDER MANAGEMENT
   GET /api/admin/orders   ← list all orders with filters
   PATCH /api/orders/<id>/status   ← update any order status

4. DELIVERY SETUP
   POST /api/admin/delivery-windows   ← create today's windows
   POST /api/admin/delivery-batches   ← assign riders to zones
   PATCH /api/admin/delivery-batches/<id>   ← add orders to batch

5. USER MANAGEMENT
   GET /api/admin/users   ← list with role/tier filters
   GET /api/admin/users/<id>   ← full profile
   PATCH /api/admin/users/<id>/role   ← promote to kitchen/rider/admin
   POST /api/admin/users/<id>/deactivate   ← block account
   POST /api/admin/hp/bulk-grant   ← award HP to multiple users

6. PROMO CODES
   POST /api/admin/promo-codes   ← create promo
   PATCH /api/admin/promo-codes/<id>   ← update/disable

7. EVENTS
   POST /api/events   ← create event
   POST /api/events/<id>/tiers   ← add ticket tiers (VIP, Regular, etc.)
   POST /api/events/<id>/qr   ← generate check-in QR
   GET /api/events/<id>/registrants   ← view all attendees
   GET /api/events/<id>/registrants?format=csv   ← download CSV
   POST /api/events/<id>/send-registrants-to-host   ← email list to host

8. REWARDS & HP
   POST /api/rewards   ← create reward
   GET /api/rewards/admin/redemptions   ← pending redemptions
   PATCH /api/rewards/admin/redemptions/<id>   ← mark fulfilled

9. MARKETPLACE
   POST /api/marketplace/admin/listings   ← create listing
   POST /api/marketplace/admin/codes/<id>   ← upload access codes

10. NOTIFICATION BLASTS
    POST /api/notifications/blasts   ← send to all users
    GET /api/notifications/blasts   ← view history

11. FEATURE FLAGS
    GET /api/admin/feature-flags   ← view all flags
    PATCH /api/admin/feature-flags/<name>   { "is_active": true/false }

12. SYSTEM SETTINGS
    GET /api/admin/settings
    PATCH /api/admin/settings/<key>   ← update runtime config
    # e.g., daily_checkin_hp, free_side_options, spin wheel prizes

13. LEADERBOARD PRIZES (after monthly reset)
    GET /api/admin/leaderboard-prizes?status=pending   ← see who won
    PATCH /api/admin/leaderboard-prizes/<id>   { "status": "fulfilled" }

14. HALL OF FAME REWARDS
    GET /api/admin/hall-of-fame-rewards
    PATCH /api/admin/hall-of-fame-rewards/<id>   { "status": "box_prepared" }

15. ANALYTICS
    GET /api/analytics/dashboard   ← top-level summary
    GET /api/analytics/sales?start_date=2026-08-01
    GET /api/analytics/export?type=orders

16. CRON JOBS (manual trigger)
    POST /api/admin/cron/birthday_hp
    POST /api/admin/cron/leaderboard_reset
    GET /api/admin/cron/status
```

---

### 35d. Kitchen Flow — Complete A-Z

```
1. LOGIN as kitchen staff
   POST /api/auth/login   { "email": "kitchen@holygrills.ng", "password": "..." }

2. CHECK LIVE QUEUE
   GET /api/kitchen/queue
   ← Returns: received[], preparing[], ready[]
   ← Poll every 30 seconds or use WebSocket if available

3. CHECK SCHEDULED ORDERS (before opening)
   GET /api/kitchen/scheduled
   ← Shows orders placed for future windows

4. CHECK TODAY'S WINDOWS
   GET /api/kitchen/windows
   ← Shows order counts per delivery window

5. PROCESS ORDERS
   # When starting to cook:
   PATCH /api/orders/<id>/status   { "status": "preparing" }

   # When done cooking:
   PATCH /api/orders/<id>/status   { "status": "ready" }

6. MANAGE CAPACITY
   PATCH /api/kitchen/settings   { "daily_order_capacity": 120 }
   # Or mark items unavailable:
   PATCH /api/menu/items/<id>   { "is_available": false }

7. BATCH SUMMARY (prepare per window)
   GET /api/kitchen/batch-summary/<window_id>
   ← Shows total quantities of each item for the window

8. FREE SIDE TAG
   ← Orders with redeemed free sides have a "🏆 Reward" tag in the queue
   ← Kitchen sees side_choice in order items

9. UPDATE SETTINGS
   PATCH /api/kitchen/settings   { "prep_time_minutes": 20 }

10. METRICS
    GET /api/kitchen/metrics   ← throughput, avg prep time
```

---

### 35e. Rider Flow — Complete A-Z

```
1. LOGIN as rider
   POST /api/auth/login   { "email": "rider@holygrills.ng", "password": "..." }

2. SET AVAILABILITY
   PATCH /api/riders/availability   { "is_available": true }

3. GET ASSIGNED BATCH
   GET /api/riders/my-batch
   ← Shows all orders in the batch with addresses

4. PICK UP FROM KITCHEN
   # For each order:
   POST /api/riders/orders/<id>/pickup
   ← Status → out_for_delivery

5. DELIVER
   # Get customer contact if needed:
   GET /api/riders/call/<order_id>   ← returns customer phone

   # Mark delivered:
   POST /api/riders/orders/<id>/deliver   { "notes": "Delivered at door" }
   ← Status → delivered
   ← Customer gets push notification + HP awarded

6. DELIVERY ATTEMPT (customer unavailable)
   POST /api/riders/orders/<id>/attempt   { "notes": "Called twice, no answer" }
   ← Status → delivery_attempted

7. VIEW HISTORY & EARNINGS
   GET /api/riders/history
   GET /api/riders/stats
   GET /api/riders/earnings

8. GO OFFLINE
   PATCH /api/riders/availability   { "is_available": false }
```

---

## Appendix A — HTTP Status Code Summary

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `400` | Bad request (validation error — check `error` field) |
| `401` | Unauthorized — missing or expired token |
| `403` | Forbidden — authenticated but wrong role |
| `404` | Not found |
| `409` | Conflict (e.g., already checked in today) |
| `422` | Unprocessable entity |
| `429` | Rate limited — slow down and retry |
| `500` | Internal server error |
| `502` | Upstream error (Resend/Paystack/OneSignal) |
| `503` | Service degraded (Supabase/Redis unreachable) |

---

## Appendix B — Role Reference

| Role | Access |
|------|--------|
| `student` | Own orders, HP, wallet, events, marketplace, rewards |
| `kitchen` | Order queue, status updates, kitchen settings |
| `rider` | Delivery batch, order status, rider stats |
| `admin` | Everything above + user management, analytics, system settings |

---

## Appendix C — HP Economy Reference

| Source | HP Type | Amount |
|--------|---------|--------|
| Food order | Pending | 1 HP per ₦10 spent |
| Order delivery (unlock) | Active | 30% of food spend unlocks pending HP |
| Welcome bonus (first order) | Active | `WELCOME_BONUS_HP` (default 50) |
| Daily check-in | Active | `daily_checkin_hp` setting (default 5) |
| Event check-in | Active | `EVENT_CHECKIN_HP` (default 40) |
| Birthday | Active | `BIRTHDAY_HP` (default 150) |
| Referral | Active | `REFERRAL_HP` (default 75) |
| Order review | Active | `REVIEW_HP` (default 20) |
| Wallet top-up | Active | `WALLET_TOPUP_HP` (default 50 per ≥₦3000) |
| Social share | Active | `SOCIAL_SHARE_HP` (default 25) |
| Graduation | Active | 1,000 HP (one-time) |
| Signup bonus | Active | `SIGNUP_BONUS_HP` (default 0) |
| Exclusive spin jackpot | Active | Up to 750 HP |
| HP bundle purchase | Active | Bundle amount |

---

## Appendix D — Resend Email Setup Checklist

1. Create a [Resend](https://resend.com) account
2. Add and verify your sending domain (e.g., `holygrills.ng`)
3. Create an API key → copy it
4. Set in Replit Secrets: `RESEND_API_KEY = re_...`
5. Set sender identity in Secrets:
   ```
   EMAIL_FROM = noreply@holygrills.ng
   EMAIL_FROM_NAME = Holy Grills
   ```
6. Verify with health check → `GET /api/health`
7. Test by placing an order → confirmation email should arrive

---

*End of Holy Grills Complete API Guide — every endpoint, every flow.*
