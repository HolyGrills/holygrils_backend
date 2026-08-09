"""
app/messages.py — Holy Grills Central Message Registry

Every user-facing string in the codebase lives here.
Import MSG (or the alias M) instead of writing string literals inline.

Usage:
    from app.messages import MSG

    return jsonify({"message": MSG.PASSWORD_CHANGED}), 200
    send_notification(title=MSG.ORDER_CONFIRMED_TITLE,
                      body=MSG.ORDER_CONFIRMED_BODY.format(order_id=...))
"""


class MSG:

    # ── API / Health ──────────────────────────────────────────────────────────
    API_VERSION              = "1.0.0"
    HEALTH_OK                = "ok"
    HEALTH_DEGRADED          = "degraded"
    HEALTH_CONNECTED         = "connected"
    HEALTH_NOT_CONFIGURED    = "not_configured"

    # ── Auth ─────────────────────────────────────────────────────────────────
    LOGGED_OUT               = "Logged out successfully"
    PASSWORD_CHANGED         = "Password changed successfully"
    ADDRESS_DELETED          = "Address deleted"
    ACCOUNT_DELETED          = "Account has been deleted. Your data will be purged within 30 days."

    # ── Order status — notification titles & bodies ───────────────────────────
    ORDER_CONFIRMED_TITLE        = "Order Confirmed!"
    ORDER_CONFIRMED_BODY         = "Your order #{order_id} is received and heading to the kitchen."

    ORDER_PREPARING_TITLE        = "Your order is being prepared"
    ORDER_PREPARING_BODY         = "The kitchen is on it! Won't be long."

    ORDER_READY_TITLE            = "Order Ready!"
    ORDER_READY_BODY             = "Your order is ready and waiting for a rider."

    ORDER_ASSIGNED_TITLE         = "Rider Assigned!"
    ORDER_ASSIGNED_BODY          = "A rider has been assigned to your order."

    ORDER_OUT_FOR_DELIVERY_TITLE = "On The Way!"
    ORDER_OUT_FOR_DELIVERY_BODY  = "Your rider has picked up your order."

    ORDER_DELIVERED_TITLE        = "Order Delivered!"
    ORDER_DELIVERED_BODY         = "Your order has been delivered. Enjoy your meal!"
    ORDER_THANK_YOU_TITLE        = "Thanks for dining with us! 🙏"
    ORDER_THANK_YOU_BODY         = "We hope you loved your {platform} meal. Looking forward to serving you again!"
    SATISFACTION_CHECK_TITLE     = "How was your meal? 😊"
    SATISFACTION_CHECK_BODY      = "We'd love your feedback — rate your {platform} experience and help us improve."
    REENGAGEMENT_NUDGE_TITLE     = "Ready for another round? 🍖"
    REENGAGEMENT_NUDGE_BODY      = "It's been a day since your last order. Come back and earn {currency} with every bite!"

    ORDER_DELIVERY_ATTEMPTED_TITLE = "Delivery Attempted"
    ORDER_DELIVERY_ATTEMPTED_BODY  = "We tried to reach you. Please respond within 30 minutes."

    ORDER_UNCLAIMED_TITLE        = "Order Unclaimed"
    ORDER_UNCLAIMED_BODY         = "Your order was not collected. Please contact us."

    ORDER_CANCELLED_TITLE        = "Order Cancelled"
    ORDER_CANCELLED_BODY         = "Your order has been cancelled. Contact us for help."

    ORDER_REFUND_TITLE           = "Your refund is being processed"
    ORDER_REFUND_BODY_WALLET     = "\u20a6{amount} has been credited to your wallet. Reason: {reason}"
    ORDER_REFUND_BODY_OTHER      = "\u20a6{amount} has been approved for refund. Reason: {reason}"
    ORDER_REFUND_SUCCESS         = "Refund processed"

    # ── Holy Points (HP) ──────────────────────────────────────────────────────
    HP_EARNED_TITLE          = "+{total_hp} {currency} Earned!"
    HP_UNLOCKED_TITLE        = "+{unlocked_hp} {currency} Unlocked!"
    HP_UNLOCKED_BODY         = "Your food order unlocked {unlocked_hp} {currency} from your pending pool."

    # ── Tier ──────────────────────────────────────────────────────────────────
    TIER_UPGRADE_TITLE       = "You reached {tier_name}!"
    TIER_UPGRADE_BODY        = "Congratulations! You've earned {tier_name} status. Enjoy your enhanced rewards."
    TIER_DROPPED_TITLE       = "Tier Update \u2014 {from_tier} \u2192 {to_tier}"
    TIER_DROPPED_BODY        = "Your grace period has ended. Keep ordering to climb back up!"
    TIER_GRACE_TITLE         = "{grace_days}-Day Grace Period Started \u2014 {tier_name}"
    TIER_GRACE_BODY          = "Your {currency} is below the {tier_name} maintenance threshold. Order within {grace_days} days to keep your tier!"

    # ── Birthday ──────────────────────────────────────────────────────────────
    BIRTHDAY_TITLE           = "Happy Birthday, {name}!"
    BIRTHDAY_BODY            = "You've received {hp} {currency} as a birthday gift! Valid for 30 days. Enjoy your special day."
    BIRTHDAY_REPORT_TITLE    = "\U0001f382 {count} Birthday{plural} This Month ({month})"

    # ── Abandoned Cart ───────────────────────────────────────────────────────
    ABANDONED_CART_TITLE          = "Your cart is waiting 🛒"
    ABANDONED_CART_BODY           = "You left items in your cart. Come back and complete your order before they sell out!"

    # ── Events ────────────────────────────────────────────────────────────────

    EVENT_CHECKIN_SUCCESS    = "Check-in successful"
    EVENT_HP_PENDING_TITLE   = "+{hp} {currency} Pending!"
    EVENT_HP_PENDING_BODY    = "You earned {currency} for attending {event_title}. Order food to unlock it!"
    EVENT_REGISTERED_TITLE   = "You're registered for {title}!"
    EVENT_REGISTERED_BODY    = "Show your ticket QR code at the door to check in and earn {currency}."
    EVENT_CATERING_TITLE     = "New Catering Request"
    EVENT_CATERING_BODY      = "{organizer} submitted a catering request for '{event_name}'"
    EVENT_CATERING_NOT_FOUND = "Catering request not found"
    EVENT_NOTES_INVALID      = "notes must be a string up to 2000 characters"
    EVENT_ASSIGNED_TO_INVALID = "assigned_to must be a valid user id"
    EVENT_ASSIGNED_TO_NOT_STAFF = "assigned_to must be an admin or staff user"
    EVENT_CAPACITY_INVALID   = "capacity must be a positive integer"
    EVENT_CAPACITY_BELOW_ISSUED = "capacity cannot be lower than tickets already issued ({issued})"
    EVENT_HP_REWARD_INVALID  = "hp_reward must be a non-negative integer"
    NO_VALID_FIELDS          = "No valid fields to update"

    # ── Marketplace ───────────────────────────────────────────────────────────
    MARKETPLACE_PURCHASE_TITLE           = "Purchase Confirmed"
    MARKETPLACE_PURCHASE_BODY            = "Purchase confirmed: {title}."
    MARKETPLACE_PURCHASE_CODE_SUFFIX     = " Your access code: {code}"
    MARKETPLACE_LOW_INVENTORY_TITLE      = "Low Code Inventory"
    MARKETPLACE_LOW_INVENTORY_BODY       = "'{title}' has only {remaining} code(s) left."
    MARKETPLACE_VENDOR_REQUEST_TITLE     = "New Vendor Listing Request"
    MARKETPLACE_VENDOR_REQUEST_BODY      = "{vendor_name} submitted a request: {service_title}"

    # ── Notifications ─────────────────────────────────────────────────────────
    NOTIF_ALL_READ           = "All notifications marked as read"
    NOTIF_TOKEN_UPDATED      = "Device token updated"
    NOTIF_TOKEN_REGISTERED   = "Device token registered"
    NOTIF_TOKEN_NOT_PROVISIONED = "push notifications not yet provisioned"
    NOTIF_BLAST_SCHEDULED    = "Blast scheduled"
    NOTIF_BLAST_NOT_FOUND    = "Notification blast not found"
    PUSH_SUBSCRIPTION_REQUIRED = "'subscription' is required"
    PUSH_SUBSCRIPTION_UPDATED  = "Push subscription updated"
    PUSH_UNSUBSCRIBED          = "Push subscription(s) deactivated"

    # ── Referrals ─────────────────────────────────────────────────────────────
    REFERRAL_NOT_FOUND       = "No referral found"
    REFERRAL_ALREADY_DONE    = "Referral already completed"
    REFERRAL_HP_EARNED_TITLE = "Referral Bonus!"
    REFERRAL_HP_EARNED_BODY  = "A friend you referred just placed their first order. You've earned {hp} {currency}!"

    # ── Storefront ────────────────────────────────────────────────────────────
    STOREFRONT_ALREADY_SUBSCRIBED = "Already subscribed"
    STOREFRONT_RESUBSCRIBED       = "Resubscribed successfully"
    STOREFRONT_UNSUBSCRIBED       = "Unsubscribed successfully"
    SECTION_NOT_FOUND             = "Storefront section not found"
    SECTION_DEACTIVATED           = "Storefront section deactivated"

    # ── Email subjects ────────────────────────────────────────────────────────
    EMAIL_ORDER_CONFIRMED    = "Your {platform} order is confirmed!"
    EMAIL_HP_EARNED          = "You just earned {currency}!"
    EMAIL_TIER_UPGRADE       = "You levelled up on {platform}!"
    EMAIL_WALLET_FUNDED      = "Wallet funded successfully"
    EMAIL_PASSWORD_RESET     = "Reset your {platform} password"
    EMAIL_BIRTHDAY_BONUS     = "Happy Birthday from {platform}! \U0001f382"
    EMAIL_REFERRAL_COMPLETED = "Your referral earned you {currency}!"
    EMAIL_ABANDONED_CART     = "Your cart is waiting for you"
    EMAIL_REWARD_REDEEMED    = "Reward redemption confirmed"
    EMAIL_TIER_GRACE         = "Your tier grace period has started"
    EMAIL_TIER_DROPPED       = "Your tier has changed"
    EMAIL_HP_EXPIRED         = "Some of your {currency} has expired"

    # ── Admin ─────────────────────────────────────────────────────────────────
    ADMIN_USER_DEACTIVATED       = "User deactivated"
    ADMIN_USER_ACTIVATED         = "User activated"
    ADMIN_USER_ALREADY_ACTIVE    = "User is already active"
    ADMIN_USER_REACTIVATED       = "User reactivated"
    ADMIN_WINDOW_CLOSED          = "Window closed"
    ADMIN_WINDOW_ALREADY_OPEN    = "Window is already open"
    ADMIN_WINDOW_REOPENED        = "Window reopened"
    ADMIN_RECOVERY_NUDGE_SENT    = "Recovery nudge sent"
    ADMIN_NUDGE_TITLE            = "You left something behind!"
    ADMIN_NUDGE_BODY             = "Your cart is still waiting \u2014 and so is your {currency}. Complete your order today."
    ADMIN_JOB_RUNNING            = "Running in background \u2014 check server logs for result"

    # ── Wallet ────────────────────────────────────────────────────────────────
    WALLET_FUNDED_TITLE          = "Wallet Funded \u20a6{amount}"
    WALLET_FUNDED_BODY           = "Your wallet has been credited with \u20a6{amount}."
    WALLET_TRANSFER_TITLE        = "Wallet Credited \u20a6{amount}"
    WALLET_TRANSFER_BODY         = "Your bank transfer of \u20a6{amount} has been confirmed."

    # ── Menu ──────────────────────────────────────────────────────────────────
    MENU_ADDON_GROUP_DELETED     = "Add-on group deleted"
    MENU_ADDON_ARCHIVED          = "Add-on archived"
    MENU_ITEM_ARCHIVED           = "Item archived"
    MENU_CATEGORY_DEACTIVATED    = "Category '{name}' deactivated"
    MENU_CAPACITY_LIMIT_REMOVED  = "Daily capacity limit removed"
    MENU_ADDON_GROUP_CREATED     = "Add-on group created"
    MENU_ADDON_GROUP_UPDATED     = "Add-on group updated"
    MENU_ADDON_GROUP_NOT_FOUND   = "Add-on group not found"
    MENU_ITEM_SOLD_OUT_TITLE     = "Item Sold Out: {name}"
    MENU_ITEM_SOLD_OUT_BODY      = "'{name}' has been marked as unavailable. Update the menu if stock is replenished."

    # ── Rewards ───────────────────────────────────────────────────────────────
    REWARD_NEW_TITLE             = "🎁 New Reward Available!"
    REWARD_NEW_BODY              = "'{name}' is now in the rewards store. Redeem it with your {currency}!"
    REWARD_REDEEMED_TITLE        = "Reward Redeemed: {name}"
    REWARD_REDEEMED_BODY         = "You spent {hp} {currency}. Our team will fulfil your reward shortly."
    REWARD_FULFILLED_TITLE       = "Reward Fulfilled"
    REWARD_STATUS_TITLE          = "Reward Update"
    REWARD_STATUS_BODY           = "Your '{name}' redemption has been {status}."

    # ── Auth errors ───────────────────────────────────────────────────────────
    AUTH_PASSWORD_TOO_SHORT      = "Password must be at least 8 characters"
    AUTH_REGISTRATION_FAILED     = "Registration failed"
    AUTH_EMAIL_PASSWORD_REQUIRED = "Email and password are required"
    AUTH_LOGIN_FAILED            = "Login failed"
    AUTH_ADDRESS_NOT_FOUND       = "Address not found"
    AUTH_USER_NOT_FOUND          = "User not found"
    AUTH_CURRENT_PASSWORD_WRONG  = "Current password is incorrect"
    AUTH_PASSWORD_UPDATE_FAILED  = "Failed to update password"
    AUTH_PASSWORD_INCORRECT      = "Password is incorrect"
    AUTH_EMAIL_REQUIRED          = "Email is required"

    # ── Admin errors ──────────────────────────────────────────────────────────
    ADMIN_WINDOW_NOT_FOUND       = "Delivery window not found"
    ADMIN_CART_NOT_FOUND         = "Cart not found or guest cart"
    ADMIN_AUDIT_LOGS_FAILED      = "Could not read audit logs: {error}"
    ADMIN_TIER_NOT_FOUND         = "Tier slug '{slug}' not found"
    ADMIN_PROMO_NOT_FOUND        = "Promo code not found"
    ADMIN_PROMO_UPDATED          = "Promo code updated"
    ADMIN_PROMO_CODE_EXISTS      = "A promo code with this code already exists"
    ADMIN_BATCH_NOT_FOUND        = "Delivery batch not found"
    ADMIN_BATCH_NO_FIELDS        = "No valid fields to update"
    ADMIN_BATCH_INVALID_STATUS   = "Invalid status — must be one of: assigned, completed, cancelled"
    ADMIN_BATCH_CANCELLED        = "Delivery batch cancelled and orders unassigned"

    # ── Rewards ───────────────────────────────────────────────────────────────
    REWARD_NOT_FOUND             = "Reward not found"
    REWARD_NOT_AVAILABLE         = "Reward not available"
    REWARD_OUT_OF_STOCK          = "Reward is out of stock"
    REWARD_EXPIRED               = "Reward has expired"
    REWARD_TIER_TOO_LOW          = "Your tier is not high enough to redeem this reward"
    REWARD_INSUFFICIENT_HP       = "Insufficient {currency}. Need {need}, have {have}"
    REWARD_DEACTIVATED           = "Reward deactivated"
    REWARD_REDEMPTION_NOT_FOUND  = "Redemption not found"
    REWARD_REDEMPTION_INVALID_STATUS = "status must be 'fulfilled' or 'rejected'"

    # ── Analytics ─────────────────────────────────────────────────────────────
    ANALYTICS_UNKNOWN_EXPORT     = "Unknown export type '{export_type}'. Valid: orders, hp_transactions, wallet_transactions, users"

    # ── HP bundles / spin ────────────────────────────────────────────────────
    HP_ADMIN_REQUIRED_FIELDS     = "user_id and amount are required"
    HP_BUNDLE_MIN                = "Minimum bundle purchase is {min_hp} {currency}"
    HP_BUNDLE_REF_REQUIRED       = "paystack_reference is required"
    HP_PAYMENT_NOT_CONFIRMED     = "Payment not confirmed. Transaction status: {status}"
    HP_PAYMENT_MISMATCH          = "Payment amount mismatch. Expected \u20a6{expected:.0f}, received \u20a6{received:.0f}"
    HP_PAYMENT_VERIFY_FAILED     = "Payment verification failed: {error}"
    # ── Riders ────────────────────────────────────────────────────────────────
    RIDER_AVAILABILITY_REQUIRED  = "'is_available' is required"
    RIDER_ORDER_NOT_FOUND        = "Order not found"
    RIDER_NO_PHONE               = "No phone number available"
    RIDER_NOT_ASSIGNED           = "No rider has been assigned to this order"
    RIDER_EARNINGS_INVALID_PERIOD = "Invalid period. Valid: today, week, month, all"

    # ── Gifts ─────────────────────────────────────────────────────────────────
    GIFT_ASSIGNED_TITLE          = "Your Gift is on the Way!"
    GIFT_ASSIGNED_BODY           = "A rider has been assigned to deliver your free hot dog gift."
    GIFT_RETURNED_TITLE          = "Gift Delivery Unsuccessful"
    GIFT_RETURNED_BODY           = "We were unable to deliver your gift. Please contact us to reschedule."
    GIFT_KITCHEN_TITLE           = "First-Order Gift Granted"
    GIFT_KITCHEN_BODY            = "Order #{order_id} qualifies for the first-order hot dog gift."

    # ── Referral signup ───────────────────────────────────────────────────────
    REFERRAL_SIGNUP_TITLE        = "Someone Used Your Referral!"
    REFERRAL_SIGNUP_BODY         = "A new user just signed up with your referral link. They need to place their first order to complete the referral."

    # ── Leaderboard ───────────────────────────────────────────────────────────
    LEADERBOARD_RANK_TITLE       = "You Made the Top 10! 🏆"
    LEADERBOARD_RANK_BODY        = "You finished #{rank} on the {period} leaderboard with {hp} {currency} earned. Keep going!"

    # ── Order cancellation / placement window ─────────────────────────────────
    ORDER_CANCEL_WINDOW_CLOSED     = "Orders cannot be cancelled once the ordering window has closed"
    ORDER_CANCEL_WRONG_STATUS      = "Only orders in 'received' status can be cancelled by the customer"
    ORDER_OUTSIDE_ORDERING_HOURS   = "Orders can only be placed during operating hours"

    # ── Webhooks ──────────────────────────────────────────────────────────────
    WEBHOOK_INVALID_SIGNATURE    = "Invalid signature"
    WEBHOOK_INVALID_JSON         = "Invalid JSON"
    WEBHOOK_OK                   = "ok"
    WEBHOOK_ALREADY_PROCESSED    = "Already processed"
    WEBHOOK_ADMIN_FAILURE_TITLE  = "Webhook Processing Failure"
    WEBHOOK_ADMIN_FAILURE_BODY   = "Event '{event_type}' (ref: {reference}) failed: {error}"

    # ── Auth extra ────────────────────────────────────────────────────────────
    AUTH_REFRESH_TOKEN_REQUIRED   = "refresh_token is required"
    AUTH_CHANGE_PW_REQUIRED       = "current_password and new_password are required"
    AUTH_CONFIRM_DELETE_REQUIRED  = "password is required to confirm account deletion"
    AUTH_ADDRESS_FIELDS_REQUIRED  = "label, line1 (or address_line), and city are required"
    AUTH_FIELD_REQUIRED           = "'{field}' is required"
    AUTH_VERIFY_EMAIL_SENT        = "If your email is not yet confirmed, a new verification link has been sent. Check your inbox."
    AUTH_VERIFY_EMAIL_MISSING     = "email is required"
    DEVICE_TOKEN_REQUIRED         = "'token' is required"
    DEVICE_TOKEN_REGISTERED       = "Device token registered"
    DEVICE_TOKEN_UPDATED          = "Device token updated"
    LOGOUT_ALL_DEVICES_OK         = "Signed out from all devices"

    # ── Events ────────────────────────────────────────────────────────────────
    # ── Ticket Tiers ──────────────────────────────────────────────────────────
    TIER_NOT_FOUND               = "Ticket tier not found"
    TIER_CAPACITY_EXCEEDED        = "This ticket tier is sold out"
    TIER_ALREADY_REGISTERED       = "You are already registered for this event"
    TIER_PRICE_INVALID            = "price_naira and price_hp must be non-negative"
    TIER_CAPACITY_INVALID_TIER    = "capacity must be a positive integer or null"
    TIER_NAME_REQUIRED            = "Tier name is required"
    TIER_DELETE_HAS_SALES         = "Cannot delete a tier with existing ticket sales"

    # ── Daily Check-in ────────────────────────────────────────────────────────
    CHECKIN_ALREADY_DONE         = "You have already checked in today"
    CHECKIN_SUCCESS              = "Daily check-in recorded"
    CHECKIN_HP_AWARDED           = "Daily check-in complete — {hp} {currency} earned"

    # ── Free Sides ────────────────────────────────────────────────────────────
    FREE_SIDE_NO_CREDITS         = "You have no free side credits"
    FREE_SIDE_REDEEMED           = "Free side credit redeemed"
    FREE_SIDE_INVALID_CHOICE     = "Invalid side choice"
    FREE_SIDE_EXPIRED            = "Your free side credits have expired"

    # ── Exclusive Spin ────────────────────────────────────────────────────────
    SPIN_NO_CREDITS              = "You have no exclusive spins available"
    SPIN_INSUFFICIENT_HP         = "Not enough {currency} to purchase an extra spin"
    SPIN_SUCCESS                 = "You spun and won: {prize}"
    SPIN_BOUGHT                  = "Extra spin purchased successfully"
    SPIN_EXPIRED                 = "Your exclusive spin has expired"

    # ── Feature Flags ─────────────────────────────────────────────────────────
    FEATURE_FLAG_NOT_FOUND       = "Feature flag not found"
    FEATURE_FLAG_UPDATED         = "Feature flag updated"
    FEATURE_FLAG_NAME_REQUIRED   = "feature_name is required"

    # ── Leaderboard Prizes / Hall of Fame ──────────────────────────────────────
    LEADERBOARD_PRIZE_FULFILLED  = "Reward marked as fulfilled"
    HOF_REWARD_FULFILLED         = "Hall of Fame reward fulfilled"
    HOF_REWARD_NOT_FOUND         = "Hall of Fame reward record not found"
    LEADERBOARD_REWARD_NOT_FOUND = "Leaderboard reward record not found"

    EVENT_NOT_FOUND              = "Event not found"

    # ── Marketplace ──────────────────────────────────────────────────────────
    LISTING_NOT_FOUND            = "Listing not found"
    LISTING_NOT_AVAILABLE        = "Listing not available"
    LISTING_OUT_OF_STOCK         = "Listing is out of stock"
    LISTING_INSUFFICIENT_HP      = "Insufficient {currency}: need {need}, have {have}"
    LISTING_NO_CODES             = "No codes available. Listing is now out of stock."
    LISTING_VENDOR_UNAVAILABLE   = "Vendor listing requests are not currently available. Please contact us directly."
    MARKETPLACE_REQUEST_SUBMITTED = "Your listing request has been submitted for review."
    MARKETPLACE_REQUEST_NOT_FOUND = "Vendor request not found"
    MARKETPLACE_REQUEST_ALREADY_REVIEWED = "This request has already been reviewed"

    # ── Menu ─────────────────────────────────────────────────────────────────
    MENU_SLUG_EXISTS             = "Slug '{slug}' already exists"
    MENU_CATEGORY_NOT_FOUND      = "Category not found"
    MENU_NO_VALID_FIELDS         = "No valid fields provided"
    MENU_ITEM_NOT_FOUND          = "Menu item not found"
    MENU_ITEM_CREATE_FAILED      = "Failed to create menu item: {error}"

    # ── Notifications ─────────────────────────────────────────────────────────
    NOTIF_NO_VALID_PREFS         = "No valid preference fields provided"

    # ── Orders ────────────────────────────────────────────────────────────────
    ORDER_WALLET_LOGIN_REQUIRED  = "Wallet payment requires a logged-in account"
    ORDER_HP_LOGIN_REQUIRED      = "{currency} redemption requires a logged-in account"
    ORDER_CREATE_FAILED          = "Order creation failed"
    ORDER_NOT_FOUND              = "Order not found"
    ORDER_ACCESS_DENIED          = "Access denied"
    ORDER_INVALID_CLAIM          = "Invalid claim token"
    ORDER_AUTH_REQUIRED          = "Authentication or claim_token required"
    ORDER_REVIEW_DELIVERED_ONLY  = "Can only review delivered orders"
    ORDER_ALREADY_REVIEWED       = "Order already reviewed"
    ORDER_ALREADY_STATUS         = "Order is already {status} and cannot be refunded"
    ORDER_ADDON_GROUP_REQUIRED   = "'{group_name}' requires at least {min_select} selection(s) for '{item_name}'"
    ORDER_ADDON_GROUP_TOO_MANY   = "'{group_name}' allows at most {max_select} selection(s) for '{item_name}'"
    ORDER_ADDON_NOT_FOUND        = "Add-on {addon_id} not found"
    ORDER_ADDON_UNAVAILABLE      = "Add-on '{name}' is not currently available"
    ORDER_ADDON_WRONG_ITEM       = "Add-on '{name}' does not belong to '{item_name}'"
    ORDER_SCHEDULE_WINDOW_REQUIRED = "'scheduled_for_window_id' is required when 'is_scheduled' is true"
    ORDER_SCHEDULE_WINDOW_INVALID  = "Selected scheduled delivery window is not open"

    # ── Storefront ────────────────────────────────────────────────────────────
    STOREFRONT_INVALID_DAY       = "Invalid day '{day}'. Must be a full weekday name."
    STOREFRONT_PROMO_INVALID     = "Invalid or expired promo code"
    STOREFRONT_PROMO_EXPIRED     = "Promo code has expired"
    STOREFRONT_PROMO_NOT_ACTIVE  = "Promo code is not yet active"
    STOREFRONT_PROMO_LIMIT       = "Promo code has reached its usage limit"
    STOREFRONT_PROMO_MIN_ORDER   = "Minimum order \u20a6{min_amount:.0f} required"

    # ── Wallet ─────────────────────────────────────────────────────────────────
    WALLET_NOT_FOUND             = "Wallet not found"
    WALLET_MIN_TOPUP             = "Minimum top-up is \u20a6{min:.0f}"
    WALLET_USER_NOT_FOUND        = "User not found"
    WALLET_PROFILE_NOT_FOUND     = "Profile not found"
    WALLET_VA_FAILED             = "Could not provision virtual account: {error}"
    WALLET_INSUFFICIENT          = "Insufficient balance. Available: \u20a6{balance:.2f}"

    # ── Cart ──────────────────────────────────────────────────────────────────
    CART_ITEM_ADDED          = "Item added to cart"
    CART_ITEM_UPDATED        = "Cart item updated"
    CART_ITEM_REMOVED        = "Item removed from cart"
    CART_CLEARED             = "Cart cleared"
    CART_ITEM_NOT_FOUND      = "Cart item not found"

    # ── Scheduled orders ──────────────────────────────────────────────────────
    ORDER_WINDOW_AT_CAPACITY     = "This delivery window is fully booked. Please choose another window."
    SCHEDULED_ORDER_DUE_TITLE    = "Scheduled Order Due"
    SCHEDULED_ORDER_DUE_BODY     = "Order #{order_id} is now due for preparation."

    # ── Order cancellation / reorder ──────────────────────────────────────────
    ORDER_CANCELLED_OK       = "Order cancelled"
    ORDER_CANNOT_CANCEL      = "Order cannot be cancelled once it is being prepared"
    ORDER_CANCEL_NOT_OWNER   = "You can only cancel your own orders"
    ORDER_REORDER_ITEMS      = "Reorder items fetched"
    ORDER_NOT_SCHEDULED_PENDING = "Order is not a pending scheduled order"

    # ── Rider ─────────────────────────────────────────────────────────────────
    RIDER_PICKUP_OK          = "Order pickup confirmed"
    RIDER_PICKUP_NOT_READY   = "Order is not ready for pickup"

    # ── Kitchen settings ──────────────────────────────────────────────────────
    KITCHEN_SETTINGS_UPDATED = "Kitchen settings updated"

    KITCHEN_SETTING_NOT_FOUND = "Kitchen setting not found"
    KITCHEN_SETTINGS_REQUIRED = "'settings' object with at least one key is required"

    # ── Generic ───────────────────────────────────────────────────────────────
    REQUIRED_FIELD_MISSING   = "Required field(s) missing"

    # ── HP transfer ───────────────────────────────────────────────────────────
    HP_TRANSFER_OK           = "{currency} transferred successfully"
    HP_TRANSFER_INSUFFICIENT = "Insufficient active {currency}. Have {have}, need {need}"
    HP_TRANSFER_SELF         = "Cannot transfer {currency} to yourself"
    HP_TRANSFER_USER_NOT_FOUND = "Recipient not found"

    # ── Saved For Later ────────────────────────────────────────────────────────
    SAVED_ITEM_ADDED         = "Item saved for later"
    SAVED_ITEM_UPDATED       = "Saved item quantity updated"
    SAVED_ITEM_REMOVED       = "Item removed from saved list"
    SAVED_ITEM_NOT_FOUND     = "Saved item not found"
    SAVED_MOVED_TO_CART      = "Item moved to cart"
    CART_MOVED_TO_SAVED      = "Item moved to saved-for-later"

    # ── Order Locks ────────────────────────────────────────────────────────────
    ORDER_LOCK_CREATED           = "Order lock created"
    ORDER_LOCK_CANCELLED         = "Order lock cancelled"
    ORDER_LOCK_RESCHEDULED       = "Order lock rescheduled"
    ORDER_LOCK_NOT_FOUND         = "Order lock not found"
    ORDER_LOCK_NOT_ACTIVE        = "Order lock is not active"
    ORDER_LOCK_DATE_REQUIRED     = "'locked_date' is required"
    ORDER_LOCK_DATE_INVALID      = "Invalid date format. Use YYYY-MM-DD"
    ORDER_LOCK_DATE_FUTURE       = "locked_date must be a future date"
    ORDER_LOCK_RESCHEDULE_LIMIT  = "This lock has already been rescheduled once"
    ORDER_LOCK_DISCOUNT_RANGE    = "discount_pct must be between 1 and {max}"
    ORDER_LOCK_REMINDER_TITLE    = "🔒 Locked Order Reminder — {days} day{plural} to go"
    ORDER_LOCK_REMINDER_BODY     = "Your {pct:.0f}% discount is reserved for {date}. Don't miss it!"
    ORDER_LOCK_EXPIRY_TITLE      = "Order Lock Expired"
    ORDER_LOCK_EXPIRY_BODY       = "Your locked order date ({date}) has passed. The lock has expired."
    ORDER_LOCK_REDEEMED_TITLE    = "🔒 Order Lock Discount Applied!"
    ORDER_LOCK_REDEEMED_BODY     = "Your {pct:.0f}% locked-date discount saved you ₦{saved:.0f} on this order!"
    ORDER_LOCK_REDEEMED_HP_TITLE = "🔒 Order Lock {currency} Reward!"
    ORDER_LOCK_REDEEMED_HP_BODY  = "You earned {hp} {currency} for placing your order on your locked date!"
    ORDER_LOCK_REMINDER_BODY_HP  = "Your {hp} {currency} reward is waiting for {date}. Place an order to claim it!"
    ORDER_LOCK_HP_AWARDED_NOTES  = "Order lock {currency} reward — {hp} {currency} awarded on locked-date order"
    BIRTHDAY_BLAST_TITLE         = "🎂 It's {name}'s Birthday Today!"
    BIRTHDAY_BLAST_BODY          = "Celebrate {name}'s birthday — tap to send them {currency} as a gift! 🎉"

    # ── First-Order Gift ───────────────────────────────────────────────────────
    GIFT_NOT_FOUND               = "Gift not found"
    GIFT_INVALID_STATUS          = "Status must be 'fulfilled' or 'cancelled'"
    GIFT_UPDATED                 = "Gift status updated"
    FIRST_ORDER_GIFT_TITLE       = "🌭 Free Hot Dog!"
    FIRST_ORDER_GIFT_BODY        = "Congrats on your first order! A free hot dog is on us. Collect it with your delivery."

    # ── System Settings ────────────────────────────────────────────────────────
    SETTING_NOT_FOUND            = "Setting not found"
    SETTING_VALUE_REQUIRED       = "'value' is required"
    SETTING_KEY_VALUE_REQUIRED   = "'key' and 'value' are required"
    SETTING_UPDATED              = "Setting updated"
    SETTING_CREATED              = "Setting created"
    SETTING_KEY_EXISTS           = "A setting with this key already exists"

    # ── Login Streak ───────────────────────────────────────────────────────────
    LOGIN_STREAK_TITLE           = "🔥 {streak}-Day Login Streak!"
    LOGIN_STREAK_BODY            = "You've logged in {streak} days in a row. Keep it up — you earned {hp} {currency}!"
    LOGIN_STREAK_RESET_TITLE     = "Streak Reset"
    LOGIN_STREAK_RESET_BODY      = "Your login streak reset to 1. Log in every day to build it back up!"

    # ── Order Share Prompt ─────────────────────────────────────────────────────
    SHARE_PROMPT_HP_TITLE        = "+{hp} {currency} for Sharing!"
    SHARE_PROMPT_HP_BODY         = "Thanks for sharing your order! {hp} {currency} added to your pending pool."
    SHARE_PROMPT_ALREADY_TODAY   = "Share reward already claimed today. Come back tomorrow!"
    SHARE_PROMPT_ORDER_NOT_FOUND = "Order not found or not yours"

    # ── Squad HP Split ─────────────────────────────────────────────────────────
    SQUAD_HP_SPLIT_TITLE         = "Squad {currency} Earned!"
    SQUAD_HP_SPLIT_BODY          = "You earned {hp} {currency} from the squad order placed by {organizer}."
    SQUAD_ORDER_ADDED_BODY       = "{organizer} added you to a squad order."
    SQUAD_INVITE_SUBJECT         = "You've been invited to join {platform}!"
    SQUAD_INVITE_BODY            = "{organizer} added you to a squad order. Create an account to start earning {currency}!"

    # ── Monthly HP Cap ─────────────────────────────────────────────────────────
    MONTHLY_HP_CAP_REACHED       = "Monthly free-activity {currency} cap reached. Cap resets on the 1st of next month."

    # ── Dormancy Win-Back ──────────────────────────────────────────────────────
    WINBACK_DAY70_TITLE          = "We miss you! 👋"
    WINBACK_DAY70_BODY           = "It's been a while! Come back and place an order to protect your {currency} balance."
    WINBACK_DAY95_TITLE          = "Your {currency} is at risk ⚠️"
    WINBACK_DAY95_BODY           = "You haven't ordered in a while. {currency} decay starts in {days} days — place an order now!"
    WINBACK_DAY118_TITLE         = "⏰ Last chance — {currency} decay starts in 2 days"
    WINBACK_DAY118_BODY          = "Your {currency} will start decaying in 2 days. Place an order to protect them!"
    WINBACK_DECAY_TITLE          = "📉 {currency} Decay Started"
    WINBACK_DECAY_BODY           = "Your {currency} balance has decreased by {amount} {currency} due to inactivity. Place an order to stop further decay."

    # ── HP Decay ──────────────────────────────────────────────────────────────
    HP_DECAY_TITLE               = "{currency} Decay — {amount} {currency} Reduced"
    HP_DECAY_BODY                = "Your {currency} decreased by {amount} due to {days} days of inactivity. Stay active to stop decay!"

    # ── HP Transfer ──────────────────────────────────────────────────────────────
    HP_TRANSFER_MIN          = "Minimum {currency} transfer is {min} {currency}"

    # ── Password change (all devices) ─────────────────────────────────────────
    PASSWORD_CHANGED_LOGGED_OUT = "Password changed. All other sessions have been signed out."

    # ── Cart validation ───────────────────────────────────────────────────────
    CART_MENU_ITEM_REQUIRED       = "'menu_item_id' is required"

    # ── Marketplace validation ─────────────────────────────────────────────────
    MARKETPLACE_CODES_REQUIRED    = "codes list is required"
    MARKETPLACE_LISTING_NOT_FOUND = "Listing not found"
    MARKETPLACE_REJECTION_REASON_REQUIRED = "rejection_reason is required when rejecting a listing"

    # ── Menu validation ────────────────────────────────────────────────────────
    MENU_ADDON_NAME_REQUIRED      = "'name' is required"
    MENU_ADDON_MAX_SELECT_INVALID = "'max_select' cannot be less than 'min_select'"
    MENU_ITEM_IDS_REQUIRED        = "'item_ids' must be a non-empty array"
    MENU_AVAILABILITY_REQUIRED    = "'is_available' is required"
    MENU_CAPACITY_POSITIVE        = "daily_order_capacity must be a positive integer"

    # ── Order validation ───────────────────────────────────────────────────────
    ORDER_ITEMS_REQUIRED           = "'items' is required"
    ORDER_DELIVERY_ADDRESS_REQUIRED = "'delivery_address' is required"
    ORDER_PAYMENT_METHOD_REQUIRED  = "'payment_method' is required"
    ORDER_STATUS_REQUIRED          = "status is required"
    ORDER_TARGET_STATUS_REQUIRED   = "target_status is required"
    ORDER_CLAIM_TOKEN_REQUIRED     = "claim_token is required"
    ORDER_REFUND_REASON_REQUIRED   = "'reason' is required"
    ORDER_REFUND_AMOUNT_INVALID    = "refund_amount must be between 0 and {max:.2f}"

    # ── Referral validation ────────────────────────────────────────────────────
    REFERRAL_FIELDS_REQUIRED      = "referred_user_id and order_id are required"

    # ── Storefront validation ──────────────────────────────────────────────────
    STOREFRONT_DAY_REQUIRED       = "day is required"
    STOREFRONT_EMAIL_REQUIRED     = "email is required"

    # ── Admin validation ───────────────────────────────────────────────────────
    ADMIN_AMOUNT_POSITIVE         = "'amount' must be a positive integer"
    ADMIN_REASON_REQUIRED         = "'reason' is required"

    # ── Generic API errors ────────────────────────────────────────────────────
    ERR_NOT_FOUND            = "Not found"
    ERR_UNAUTHORIZED         = "Unauthorized"
    ERR_FORBIDDEN            = "Access denied"
    ERR_BAD_REQUEST          = "Bad request"
    ERR_SERVER               = "An unexpected error occurred. Please try again."

    # ── Event (checkin fallback path) ─────────────────────────────────────────
    EVENT_NO_TICKET              = "No ticket found for this event"
    EVENT_INVALID_QR             = "Invalid QR token"
    EVENT_ALREADY_CHECKED_IN     = "Already checked in to this event"
    EVENT_AT_CAPACITY            = "Event is at full capacity"

    # ── Paid event ticket ─────────────────────────────────────────────────────
    PAID_EVENT_PAYMENT_REQUIRED  = "payment_method is required for paid events (wallet or card)"
    PAID_EVENT_HP_USED           = "Ticket issued. {hp} {currency} deducted, ₦{cash:.0f} charged."
    PAID_EVENT_CASH_ONLY         = "Ticket issued. Full price ₦{total:.0f} charged (insufficient {currency})."

    # ── HP Transfer — recipient notification ──────────────────────────────────
    HP_TRANSFER_RECEIVED_TITLE   = "You received {amount} {currency}! 🎉"
    HP_TRANSFER_RECEIVED_BODY    = "{sender} sent you {amount} {currency}."

    # ── Graduation ────────────────────────────────────────────────────────────
    GRADUATION_PROFILE_NOT_FOUND = "Profile not found"
    GRADUATION_ALREADY_CLAIMED   = "Graduation {currency} has already been claimed"
    GRADUATION_LEVEL_REQUIRED    = "Graduation claim requires academic_level {required}+. Your level: {actual}."
    GRADUATION_BONUS_TITLE       = "🎓 Graduation Bonus Claimed!"
    GRADUATION_BONUS_BODY        = "{name}, you've earned {hp} {currency} for reaching Level {level}!"
    GRADUATION_CLAIMED_OK        = "Graduation {currency} claimed successfully"

    # ── HP flash sale ─────────────────────────────────────────────────────────
    HP_FLASH_NO_ACTIVE_SALE      = "No active flash sale for this reward"
    HP_FLASH_WINDOW_CLOSED       = "Flash sale window has closed"
    HP_FLASH_LIMIT_REACHED       = "Flash sale limit of {qty} redemptions reached"
    HP_INSUFFICIENT              = "Insufficient {currency}: have {have}, need {need}"
    HP_FLASH_INSUFFICIENT        = "Insufficient {currency} for flash deal: need {need}, have {have}"

    # ── HP Transfer (min orders) ──────────────────────────────────────────────
    HP_TRANSFER_MIN_ORDERS       = "{currency} transfer requires at least {min_orders} completed orders. You have {completed}."

    # ── Hall of Fame ──────────────────────────────────────────────────────────
    HALL_OF_FAME_TITLE           = "🏛️ Hall of Fame!"
    HALL_OF_FAME_BODY            = "Congratulations! You've reached the top 3 in three different months — you've been inducted into the {platform} Hall of Fame!"

    # ── Phase 3 notification titles/bodies ────────────────────────────────────
    LEADERBOARD_PRIZE_TITLE      = "🎁 Your Leaderboard Prize is Ready!"
    LEADERBOARD_PRIZE_BODY       = "You ranked #{rank} in {period}! You've earned: {prize}. Your reward is being processed."
    EXCLUSIVE_SPIN_WON_TITLE     = "🎡 Spin Result!"
    EXCLUSIVE_SPIN_WON_BODY      = "You spun the exclusive wheel and won: {prize}! Check the app for details."
    DAILY_CHECKIN_TITLE          = "✅ Daily Check-in!"
    DAILY_CHECKIN_BODY           = "You've checked in for today and earned {hp} {currency}. Keep the streak going!"
    ADMIN_HOF_INDUCTION_TITLE    = "🏅 New Hall of Fame Inductee"
    ADMIN_HOF_INDUCTION_BODY     = "{inducted_name} has been inducted into the Hall of Fame! Fulfil their reward box when ready."

    # ── Membership Anniversary ────────────────────────────────────────────────
    ANNIVERSARY_FALLBACK_NAME    = "Valued Member"
    ANNIVERSARY_TITLE            = "🎉 {months}-Month Anniversary!"
    ANNIVERSARY_BODY             = "Happy {months}-month anniversary, {name}! You've earned {hp} {currency} as a thank-you."

    # ── Login streak week ─────────────────────────────────────────────────────
    LOGIN_STREAK_WEEK_COMPLETE_TITLE = "Week {week} Streak Complete! 🔥"
    LOGIN_STREAK_WEEK_COMPLETE_BODY  = "You earned {hp} {currency} for completing your check-in week. Keep it going!"

    # ── Login streak reclaim ──────────────────────────────────────────────────
    LOGIN_STREAK_RECLAIM_TITLE       = "Missed Day Recovered ✅"
    LOGIN_STREAK_RECLAIM_BODY_ORDER  = "Your order recovered your missed check-in today. Streak saved!"
    LOGIN_STREAK_RECLAIM_BODY_TOPUP  = "Your top-up recovered your missed check-in today. Streak saved!"

    # ── Order streak ──────────────────────────────────────────────────────────
    ORDER_STREAK_TITLE               = "Order Streak: {weeks} Week{plural}! 🔥"
    ORDER_STREAK_BODY                = "You earned {hp} {currency} for ordering every week for {weeks} week{plural}!"
    LOGIN_STREAK_CYCLE_FAILED_TITLE  = "💔 Check-In Cycle Reset"
    LOGIN_STREAK_CYCLE_FAILED_BODY   = "Too many missed days this week — you're back to Week 1. Fresh start! 💪"
    MULTIPLIER_LIVE_TITLE            = "🔥 {currency} Multiplier Is LIVE!"
    MULTIPLIER_LIVE_BODY             = "Earn {multiplier}x {currency} on all food orders right now — don't miss it!"
    MARKETPLACE_PURCHASE_STATUS_TITLE = "🛒 Purchase Update"
    MARKETPLACE_PURCHASE_STATUS_BODY  = "Your {title} order is now marked as {status}."

    # ── Validation — generic field-level ─────────────────────────────────────
    FIELD_MUST_BE_INTEGER        = "{field} must be an integer"
    FIELD_MUST_BE_NONEMPTY_STR   = "{field} must be a non-empty string"
    MARKETPLACE_STATUS_INVALID   = "'status' must be one of: active, rejected, archived"
    MARKETPLACE_APPROVE_REJECT   = "'status' must be 'approved' or 'rejected'"

    # ── Wallet / Payment errors ───────────────────────────────────────────────
    ORDER_WALLET_INSUFFICIENT    = "Insufficient wallet balance: need ₦{need:.2f}"
    ORDER_WALLET_PAYMENT_FAILED  = "Wallet payment failed: {error}"

    # ── Order / Menu validation errors ────────────────────────────────────────
    ORDER_KITCHEN_AT_CAPACITY    = "The kitchen has reached its daily order capacity. Please try again tomorrow or check back later."
    ORDER_ITEMS_EMPTY            = "Order must contain at least one item"
    ORDER_MENU_ITEM_NOT_FOUND    = "Menu item {id} not found"
    ORDER_MENU_ITEM_UNAVAILABLE  = "'{name}' is not currently available"
    ORDER_MENU_ITEM_SOLD_OUT_TODAY = "'{name}' only has {remaining} serving(s) left today"
    ORDER_VARIATION_UNAVAILABLE  = "Variation option '{name}' is not currently available"
    ORDER_DELIVERY_WINDOW_NOT_OPEN = "Selected delivery window is not open"
    ORDER_PROMO_INVALID          = "Promo code '{code}' is not valid"
    ORDER_PROMO_MIN_ORDER        = "Minimum order value ₦{min_amount:.0f} required for this code"


    # ── Notification titles & bodies (push / in-app template registry) ─────────
    # These are the display strings for push notifications and in-app inbox.
    # They are referenced by notification_templates.py — never hardcoded there.

    # Auth / Account (personalized)
    NOTIF_PASSWORD_CHANGED_TITLE    = "Security Alert — Password Changed"
    NOTIF_PASSWORD_CHANGED_BODY     = "Your password was just changed, {name}. If this wasn't you, contact us immediately."
    NOTIF_ACCOUNT_DEACTIVATED_TITLE = "Account Deactivated"
    NOTIF_ACCOUNT_DEACTIVATED_BODY  = "Hi {name}, your {platform} account has been deactivated. Contact support if this was a mistake."
    NOTIF_ACCOUNT_REACTIVATED_TITLE = "You're Back, {name}!"
    NOTIF_ACCOUNT_REACTIVATED_BODY  = "Your {platform} account is active again. Welcome back!"
    NOTIF_ACCOUNT_DELETED_TITLE     = "Account Deleted"
    NOTIF_ACCOUNT_DELETED_BODY      = "Hi {name}, your account has been deleted. Your data will be purged within 30 days."

    # Login streak (personalized)
    NOTIF_LOGIN_STREAK_CHECKIN_TITLE  = "\U0001f525 {streak_count}-Day Streak!"
    NOTIF_LOGIN_STREAK_CHECKIN_BODY   = "You checked in {streak_count} days in a row, {name}. Keep it up!"
    NOTIF_LOGIN_STREAK_CYCLE_FAILED_TITLE = "\U0001f494 Check-In Cycle Reset"
    NOTIF_LOGIN_STREAK_CYCLE_FAILED_BODY  = "Too many missed days this week, {name} — you're back to Week 1. Fresh start! \U0001f4aa"
    NOTIF_LOGIN_STREAK_RECLAIM_TITLE  = "Missed Day Recovered \u2705"
    NOTIF_LOGIN_STREAK_RECLAIM_BODY   = "Your missed check-in was recovered, {name}. Streak saved!"

    # Reviews (personalized)
    REVIEW_REQUEST_TITLE       = "How was your order? \u2b50"
    REVIEW_REQUEST_BODY        = "Order #{order_id} is delivered! Leave a review and earn {currency}."
    REVIEW_SUBMITTED_TITLE     = "Review Submitted"
    REVIEW_SUBMITTED_BODY      = "Thanks for your feedback, {name}! Your review on order #{order_id} is live."

    # HP Earned — source-specific (personalized)
    HP_EARNED_FOOD_BODY        = "You earned {hp} {currency} from your food order, {name}. Keep ordering to unlock more!"
    HP_EARNED_WELCOME_TITLE    = "Welcome Bonus!"
    HP_EARNED_WELCOME_BODY     = "You earned {hp} {currency} for your first order delivery. Welcome to {platform}, {name}!"
    HP_EARNED_TOPUP_TITLE      = "+{hp} {currency} Earned!"
    HP_EARNED_TOPUP_BODY       = "You earned {hp} {currency} for topping up your wallet, {name}."
    HP_EARNED_ANNIVERSARY_BODY = "Membership anniversary bonus — {hp} {currency} added to your account, {name}!"
    HP_EARNED_SOCIAL_TITLE     = "+{hp} {currency} for Following Us!"
    HP_EARNED_SOCIAL_BODY      = "Thanks for following us on {platform}, {name}! {hp} {currency} has been added to your account."
    HP_EARNED_LOGIN_BODY       = "You earned {hp} {currency} for your login streak, {name}. Keep checking in!"
    HP_EARNED_CHALLENGE_BODY   = "You earned {hp} {currency} for completing a challenge, {name}!"

    # HP Gift (personalized)
    HP_GIFT_RECEIVED_TITLE     = "\U0001f381 {currency} Gift Received!"
    HP_GIFT_RECEIVED_BODY      = "{gift_sender} sent you {hp} {currency} as a gift, {name}!"
    HP_GIFT_SENT_TITLE         = "{currency} Gift Sent"
    HP_GIFT_SENT_BODY          = "You sent {hp} {currency} to a friend successfully."

    # Flash sale (personalized)
    FLASH_REDEEMED_TITLE       = "Flash Deal Redeemed!"
    FLASH_REDEEMED_BODY        = "You redeemed a {discount_pct}% discount on your order, {name}. Enjoy!"

    # HP Decay warning (personalized, separate from winback body copy)
    HP_DECAY_WARNING_TITLE     = "\u26a0\ufe0f Your {currency} is at Risk, {name}"
    HP_DECAY_WARNING_BODY      = "Place an order soon to protect your {currency} balance — decay starts in {days} days!"

    # Tier (personalized)
    TIER_GRACE_ENDED_TITLE     = "Grace Period Ended — Tier Changed"
    TIER_GRACE_ENDED_BODY      = "Hi {name}, your grace period ended. You've moved from {from_tier} to {to_tier}. Keep ordering to climb back!"

    # Events — user-facing (personalized)
    EVENT_TICKET_PURCHASED_TITLE = "Ticket Confirmed! \U0001f3ab"
    EVENT_TICKET_PURCHASED_BODY  = "You're all set for {event_title}, {name}. Show your QR code at the door."
    EVENT_CATERING_SUBMITTED_TITLE = "Catering Request Submitted"
    EVENT_CATERING_SUBMITTED_BODY  = "Your catering request for '{event_title}' has been submitted, {name}. We'll be in touch soon."
    EVENT_CATERING_STATUS_TITLE  = "Catering Request Update"
    EVENT_CATERING_STATUS_BODY   = "Your catering request for '{event_title}' has been updated, {name}."

    # Marketplace — user-facing (personalized)
    MARKETPLACE_ACCESS_CODE_TITLE = "Your Access Code"
    MARKETPLACE_ACCESS_CODE_BODY  = "Here's your access code for {reward_name}: {code}"
    MARKETPLACE_ESCROW_TITLE      = "Purchase Update"
    MARKETPLACE_ESCROW_BODY       = "Your order for {reward_name} has been updated, {name}."
    VENDOR_REQUEST_SUBMITTED_TITLE = "Listing Request Submitted"
    VENDOR_REQUEST_SUBMITTED_BODY  = "Hi {name}, your vendor listing request has been submitted for review."
    VENDOR_REQUEST_APPROVED_TITLE  = "Listing Request Approved! \U0001f389"
    VENDOR_REQUEST_APPROVED_BODY   = "Hi {name}, your vendor listing is approved and now live on the marketplace."
    VENDOR_REQUEST_REJECTED_TITLE  = "Listing Request Update"
    VENDOR_REQUEST_REJECTED_BODY   = "Hi {name}, your vendor listing request was not approved at this time. Contact us for details."

    # Wallet — channel-specific titles (personalized)
    WALLET_FUNDED_CARD_TITLE       = "Wallet Funded \u20a6{amount}"
    WALLET_FUNDED_CARD_BODY        = "Hi {name}, \u20a6{amount} has been credited to your wallet via card."
    WALLET_FUNDED_BANK_TITLE       = "Wallet Funded \u20a6{amount}"
    WALLET_FUNDED_BANK_BODY        = "Hi {name}, your bank transfer of \u20a6{amount} has been confirmed."
    WALLET_LOW_TITLE               = "Wallet Balance Low"
    WALLET_LOW_BODY                = "Hi {name}, your wallet balance is running low. Top up to keep ordering without interruption."

    # Rider-specific (personalized)
    RIDER_BATCH_TITLE              = "New Batch Assigned"
    RIDER_BATCH_BODY               = "Batch {batch_id} has been assigned to you. Check the app for order details."
    RIDER_ORDER_READY_TITLE        = "Order Ready for Pickup"
    RIDER_ORDER_READY_BODY         = "Order #{order_id} is ready at the kitchen. Head over for pickup."
    RIDER_PICKUP_CONFIRMED_TITLE   = "Pickup Confirmed"
    RIDER_PICKUP_CONFIRMED_BODY    = "You've confirmed pickup of order #{order_id}. Safe ride!"
    RIDER_DELIVERY_CONFIRMED_TITLE = "Delivery Confirmed \u2705"
    RIDER_DELIVERY_CONFIRMED_BODY  = "Order #{order_id} marked as delivered. Great job!"
    RIDER_DELIVERY_ATTEMPTED_TITLE = "Delivery Attempted"
    RIDER_DELIVERY_ATTEMPTED_BODY  = "You marked order #{order_id} as delivery attempted. Customer has been notified."
    RIDER_EARNINGS_TITLE           = "Earnings Update"
    RIDER_EARNINGS_BODY            = "Your earnings have been updated. Check the app for your latest balance."

    # Kitchen / operational (personalized — rider/staff context)
    KITCHEN_ORDER_TITLE            = "New Order Received"
    KITCHEN_ORDER_BODY             = "Order #{order_id} has been placed and needs preparation."
    KITCHEN_BATCH_TITLE            = "Batch Ready"
    KITCHEN_BATCH_BODY             = "Batch {batch_id} is ready for rider pickup."

    # Leaderboard (personalized)
    LEADERBOARD_TOP4_TITLE         = "Top 4! \U0001f3c5"
    LEADERBOARD_TOP4_BODY          = "Incredible, {name}! You finished in the top 4 on the {period} leaderboard. You're in contention for the Hall of Fame!"
    SQUAD_LEADERBOARD_TITLE        = "Squad Leaderboard Update"
    SQUAD_LEADERBOARD_BODY         = "Your squad's leaderboard rank has changed. Check the app!"
    HALL_OF_FAME_CARD_TITLE        = "\U0001f3db\ufe0f Share Your Achievement!"
    HALL_OF_FAME_CARD_BODY         = "You've been inducted into the Hall of Fame, {name}! Share your achievement card."

    # Order streak (personalized)
    ORDER_STREAK_BROKEN_TITLE      = "Order Streak Broken \U0001f494"
    ORDER_STREAK_BROKEN_BODY       = "Your order streak has ended, {name}. Start a new one today!"

    # Graduation (personalized)
    GRADUATION_DECLARED_TITLE      = "\U0001f393 Graduation Declared!"
    GRADUATION_DECLARED_BODY       = "Hi {name}, you've declared graduation. Complete the process to claim your {currency} bonus."

    # Share (personalized)
    SHARE_COMPLETED_TITLE          = "Share Recorded!"
    SHARE_COMPLETED_BODY           = "Thanks for sharing your {platform} experience, {name}!"

    # Multiplier events (personalized)
    MULTIPLIER_EXPIRES_TITLE       = "\u23f0 {currency} Multiplier Ending Soon!"
    MULTIPLIER_EXPIRES_BODY        = "The {currency} multiplier event ends soon, {name}. Place an order now to earn bonus {currency}!"
    MULTIPLIER_REMINDER_TITLE      = "\U0001f525 {currency} Multiplier Is Still LIVE!"
    MULTIPLIER_REMINDER_BODY       = "Don't forget, {name} — you're still earning {multiplier}x {currency} on food orders!"

    # Scheduled content — now personalized (moved from non-personalized)
    DAILY_GREETING_TITLE           = "Good Morning, {name}! \u2600\ufe0f"
    DAILY_GREETING_BODY            = "Start your day right — check out today's menu and earn {currency} with every order!"
    WEEKLY_PRAYER_TITLE            = "\U0001f64f Weekly Prayer"
    WEEKLY_PRAYER_BODY             = "May this week bring you blessings, good food, and great opportunities, {name}. Have a wonderful week!"

    # Squads (personalized)
    SQUAD_ORDER_READY_TITLE        = "Squad Order Ready!"
    SQUAD_ORDER_READY_BODY         = "Your squad order is ready and being dispatched, {name}!"
    GUEST_ORDER_CLAIMED_TITLE      = "Guest Order Linked!"
    GUEST_ORDER_CLAIMED_BODY       = "Your guest order #{order_id} has been linked to your account, {name}."

    # Scheduled orders (personalized)
    SCHEDULED_ORDER_PROMOTED_TITLE = "Scheduled Order Confirmed!"
    SCHEDULED_ORDER_PROMOTED_BODY  = "Your scheduled order #{order_id} has been added to the next delivery batch."
    SCHEDULED_ORDER_CANCELLED_TITLE = "Scheduled Order Cancelled"
    SCHEDULED_ORDER_CANCELLED_BODY  = "Hi {name}, your scheduled order #{order_id} has been cancelled."

    # Non-personalized notifications (include_name=False)
    NOTIF_WELCOME_TITLE            = "Welcome to {platform}!"
    NOTIF_WELCOME_BODY             = "You're in! Start exploring the menu and earn {currency} with every order."
    NOTIF_EMAIL_VERIFY_TITLE       = "Verify Your Email"
    NOTIF_EMAIL_VERIFY_BODY        = "Click the link in your email to activate your {platform} account."
    NOTIF_PASSWORD_RESET_TITLE     = "Password Reset Request"
    NOTIF_PASSWORD_RESET_BODY      = "We received a request to reset your password. Check your email for the reset link. If you didn't request this, ignore this message."
    NOTIF_SYSTEM_TITLE             = "\U0001f4e2 System Announcement"
    NOTIF_SYSTEM_BODY              = "An important update from {platform}. Check the app for details."
    NOTIF_SQUAD_INVITE_TITLE       = "You've Been Invited!"
    NOTIF_SQUAD_INVITE_BODY        = "You've been invited to join a {platform} squad order. Check the app to join."
    NOTIF_SQUAD_MEMBER_ADDED_TITLE = "You're in a Squad Order!"

    # ── Admin API errors ──────────────────────────────────────────────────────
    ADMIN_INVALID_ROLE             = "Invalid role. Must be one of: {roles}"
    ADMIN_FIELD_REQUIRED           = "'{field}' is required"
    ADMIN_FIELD_MUST_BE_POSITIVE   = "{field} must be a positive integer"
    ADMIN_UNKNOWN_CRON_JOB         = "Unknown cron job: '{job}'"

    # ── Event messages ────────────────────────────────────────────────────────
    EVENT_DELETED                  = "Event '{title}' deleted"



# Short alias
M = MSG


# ── Message resolver ──────────────────────────────────────────────────────────
import os as _os


class _PassthroughDict(dict):
    """Return '{key}' for any missing key so unrelated placeholders pass through."""
    def __missing__(self, key):
        return '{' + key + '}'


def resolve_msg(text: str, **kwargs) -> str:
    """Resolve {currency} and {platform} from env, plus caller-supplied kwargs.

    Unknown placeholders (e.g. {order_id}, {name}) are left as-is so the
    caller doesn't need to supply every placeholder in advance.

    Usage (replaces raw MSG.CONSTANT.format(...) calls in route/service code):
        resolve_msg(MSG.HP_INSUFFICIENT, have=bal, need=cost)
    """
    if '{' not in text:
        return text
    defaults = {
        'currency': _os.environ.get('HP_CURRENCY_NAME', 'HP'),
        'platform': _os.environ.get('APP_NAME', 'Holy Grills'),
    }
    defaults.update(kwargs)
    return text.format_map(_PassthroughDict(defaults))
