"""
Email dispatch via Resend (https://resend.com).
All calls are fire-and-forget. Falls back gracefully if RESEND_API_KEY is not configured.

Resend REST API: POST https://api.resend.com/emails
Auth: Authorization: Bearer <RESEND_API_KEY>
"""

import os
import requests
from flask import current_app
from app.messages import MSG
from app.utils.logger import get_logger

logger = get_logger(__name__)

RESEND_BASE = "https://api.resend.com"

TEMPLATES = {
    "order_confirmed": {
        "subject": MSG.EMAIL_ORDER_CONFIRMED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your order #{d.get('order_id','')[:8].upper()} has been received and is heading to the kitchen.

Total: ₦{d.get('total', 0):,.0f}
Estimated delivery: {d.get('window_label', 'your selected window')}

Track your order in the app.

— {d.get('app_tagline', '')}
""",
    },
    "hp_earned": {
        "subject": MSG.EMAIL_HP_EARNED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

You earned {d.get('hp', 0)} {d.get('currency', 'HP')} on your recent order. Keep ordering to build your {d.get('currency', 'HP')} balance and unlock rewards!

Your balance: {d.get('active_hp', 0)} {d.get('currency', 'HP')} active | {d.get('pending_hp', 0)} {d.get('currency', 'HP')} pending

— {d.get('app_tagline', '')}
""",
    },
    "tier_upgrade": {
        "subject": MSG.EMAIL_TIER_UPGRADE,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Congratulations — you've reached {d.get('tier_name', '')} tier!

Your new benefits:
{d.get('perks', '')}

Keep earning to maintain your status.

— {d.get('app_tagline', '')}
""",
    },
    "wallet_funded": {
        "subject": MSG.EMAIL_WALLET_FUNDED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your {d.get('app_name', '')} wallet has been credited with ₦{d.get('amount', 0):,.0f}.

New balance: ₦{d.get('new_balance', 0):,.0f}

— {d.get('app_tagline', '')}
""",
    },
    "password_reset": {
        "subject": MSG.EMAIL_PASSWORD_RESET,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

We received a request to reset your password. Click the link below:

{d.get('reset_link', '')}

This link expires in 1 hour. If you didn't request this, ignore this email.

— {d.get('app_tagline', '')}
""",
    },
    "birthday_bonus": {
        "subject": MSG.EMAIL_BIRTHDAY_BONUS,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Happy Birthday! As a gift, we've added {d.get('hp', 150)} {d.get('currency', 'HP')} to your account.

Head to the app and treat yourself on us!

— {d.get('app_tagline', '')}
""",
    },
    "referral_completed": {
        "subject": MSG.EMAIL_REFERRAL_COMPLETED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Great news — a friend you referred just placed their first order on {d.get('app_name', '')}.

You've earned {d.get('hp', 75)} {d.get('currency', 'HP')} (active, no monthly cap). Spend it on your next order!

— {d.get('app_tagline', '')}
""",
    },
    "abandoned_cart": {
        "subject": MSG.EMAIL_ABANDONED_CART,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

You left some items in your cart. Come back and complete your order — your {d.get('currency', 'HP')} is waiting!

{d.get('items_summary', '')}

— {d.get('app_tagline', '')}
""",
    },
    "reward_redeemed": {
        "subject": MSG.EMAIL_REWARD_REDEEMED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

You redeemed: {d.get('reward_name', '')} for {d.get('hp_spent', 0)} {d.get('currency', 'HP')}.

Our team will fulfil your reward within {d.get('fulfilment_time', '24 hours')}.

— {d.get('app_tagline', '')}
""",
    },
    "tier_grace_period": {
        "subject": MSG.EMAIL_TIER_GRACE,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your {d.get('currency', 'HP')} activity has dipped below the {d.get('tier_name', 'your tier')} threshold.
You have {d.get('grace_days', 7)} days to place an order and keep your tier status.

— {d.get('app_tagline', '')}
""",
    },
    "tier_dropped": {
        "subject": MSG.EMAIL_TIER_DROPPED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Your grace period has ended and your tier has been updated.
Keep ordering to climb back up!

— {d.get('app_tagline', '')}
""",
    },
    "hp_expired": {
        "subject": MSG.EMAIL_HP_EXPIRED,
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

{d.get('amount', 0)} {d.get('currency', 'HP')} has decayed due to {d.get('inactivity_days', 120)} days of inactivity.
Place an order to protect your remaining balance!

— {d.get('app_tagline', '')}
""",
    },
    "monthly_birthday_report": {
        "subject": lambda d: f"🎂 Birthday Report — {d.get('month', 'This Month')} ({d.get('count', 0)} users)",
        "body": lambda d: f"""
Hi {d.get('name', 'Admin')},

Here are the {d.get('app_name', '')} users with birthdays in {d.get('month', 'this month')}:

{d.get('summary_text', 'No birthdays this month.')}

Total: {d.get('count', 0)} user{'s' if d.get('count', 0) != 1 else ''}

You can use this list to send birthday wishes, create flyers, or DM them directly.

— {d.get('app_tagline', '')}
""",
    },
    "event_tickets_export": {
        "subject": lambda d: f"Event Registrants — {d.get('event_title', 'Event')}",
        "body": lambda d: f"""
Hi {d.get('name', 'there')},

Please find attached the registrant list for {d.get('event_title', 'your event')}.

Total registrants: {d.get('count', 0)}

{d.get('registrant_table', '')}

— {d.get('app_tagline', '')}
""",
    },
}


def _resend_api_key() -> str:
    """Return RESEND_API_KEY from env. Empty string if not configured."""
    return os.environ.get("RESEND_API_KEY", "")


def _build_html(name: str, body_text: str, app_tagline: str) -> str:
    """Wrap plain-text body in a minimal responsive HTML shell."""
    body_html = body_text.strip().replace("\n", "<br>")
    return (
        f"<html><body style='font-family:sans-serif;max-width:600px;margin:auto;padding:20px'>"
        f"<p>Hi {name},</p>"
        f"<p>{body_html}</p>"
        f"<br><p style='color:#888;font-size:12px'>— {app_tagline}</p>"
        f"</body></html>"
    )


def send_email(to_email: str, to_name: str, template_key: str, data: dict = None) -> bool:
    """
    Send a transactional email via Resend.
    Returns True on success, False on failure (never raises).
    """
    api_key = _resend_api_key()
    if not api_key:
        logger.debug("send_email: RESEND_API_KEY not configured — skipping email to %s", to_email)
        return False

    template = TEMPLATES.get(template_key)
    if not template:
        logger.warning("send_email: unknown template_key '%s'", template_key)
        return False

    data = data or {}
    data.setdefault("name", to_name)
    data.setdefault("app_tagline", os.environ.get("APP_TAGLINE", "Holy Grills FUTA"))
    data.setdefault("app_name", os.environ.get("APP_NAME", "Holy Grills"))
    data.setdefault("currency", os.environ.get("HP_CURRENCY_NAME", "HP"))

    from_email = os.environ.get("EMAIL_FROM", "noreply@holygrills.ng")
    from_name  = os.environ.get("EMAIL_FROM_NAME", "Holy Grills")

    subject_tpl = template["subject"]
    subject = subject_tpl(data) if callable(subject_tpl) else subject_tpl

    body_text = template["body"](data)

    # Resolve {platform} and {currency} placeholders
    _app_name = data.get("app_name", os.environ.get("APP_NAME", "Holy Grills"))
    _currency  = data.get("currency", os.environ.get("HP_CURRENCY_NAME", "HP"))
    if isinstance(subject, str):
        subject = subject.replace("{platform}", _app_name).replace("{currency}", _currency)
    body_text = body_text.replace("{platform}", _app_name).replace("{currency}", _currency)

    html_body = _build_html(to_name or "there", body_text, data.get("app_tagline", ""))

    payload = {
        "from": f"{from_name} <{from_email}>",
        "to":   [to_email],
        "subject": subject,
        "html": html_body,
    }

    try:
        from app.utils.retry import with_retry

        @with_retry(max_attempts=3, backoff=0.5)
        def _post():
            return requests.post(
                f"{RESEND_BASE}/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
                json=payload,
                timeout=10,
            )

        resp = _post()
        if resp.status_code not in (200, 201):
            logger.warning("Resend email error %s for %s: %s", resp.status_code, to_email, resp.text[:200])
            return False
        return True
    except Exception as e:
        logger.error("Email send failed for %s: %s", to_email, e)
        return False


def send_email_raw(to_email: str, to_name: str, subject: str, html_body: str) -> bool:
    """
    Send a raw HTML email via Resend (no template lookup).
    Used for dynamically assembled bodies (birthday report, event export, etc.).
    Returns True on success, False on failure (never raises).
    """
    api_key = _resend_api_key()
    if not api_key:
        logger.debug("send_email_raw: RESEND_API_KEY not configured — skipping email to %s", to_email)
        return False

    from_email = os.environ.get("EMAIL_FROM", "noreply@holygrills.ng")
    from_name  = os.environ.get("EMAIL_FROM_NAME", "Holy Grills")

    payload = {
        "from": f"{from_name} <{from_email}>",
        "to":   [to_email],
        "subject": subject,
        "html": html_body,
    }

    try:
        from app.utils.retry import with_retry

        @with_retry(max_attempts=3, backoff=0.5)
        def _post():
            return requests.post(
                f"{RESEND_BASE}/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
                json=payload,
                timeout=10,
            )

        resp = _post()
        if resp.status_code not in (200, 201):
            logger.warning("Resend raw email error %s for %s: %s", resp.status_code, to_email, resp.text[:200])
            return False
        return True
    except Exception as e:
        logger.error("Raw email send failed for %s: %s", to_email, e)
        return False


def get_user_email_and_name(user_id: str) -> tuple:
    """Fetch user email + name from Supabase profiles table."""
    from app.db import get_db
    db = get_db()
    try:
        profile = (
            db.table("profiles")
            .select("full_name,email")
            .eq("id", user_id)
            .single()
            .execute()
        )
        if profile:
            return profile.get("email", ""), profile.get("full_name", "")
        return "", ""
    except Exception:
        return "", ""
