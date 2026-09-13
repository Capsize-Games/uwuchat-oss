"""Email sending utilities for the auth extension.

Supports SMTP for development and transactional email services (SendGrid,
Mailgun, Postmark, etc.) for production.

Configuration (environment variables):
    AIRUNNER_SMTP_HOST       — SMTP server hostname
    AIRUNNER_SMTP_PORT       — SMTP server port (default: 587)
    AIRUNNER_SMTP_USER       — SMTP username
    AIRUNNER_SMTP_PASSWORD   — SMTP password
    AIRUNNER_SMTP_FROM       — From address (default: noreply@airunner.local)
    AIRUNNER_SMTP_USE_TLS    — Whether to use STARTTLS (default: true)
    AIRUNNER_SITE_URL        — Public-facing site URL for links (default: http://localhost:5173)

If SMTP is not configured, the module degrades gracefully: it logs a warning
and does not attempt to send, allowing accounts to be created without
verification in local development.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from string import Template

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

SMTP_HOST = os.environ.get("AIRUNNER_SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("AIRUNNER_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("AIRUNNER_SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("AIRUNNER_SMTP_PASSWORD", "").strip()
SMTP_FROM = os.environ.get("AIRUNNER_SMTP_FROM", "noreply@airunner.local").strip()
SMTP_USE_TLS = os.environ.get("AIRUNNER_SMTP_USE_TLS", "true").strip().lower() in ("true", "1", "yes")
SITE_URL = os.environ.get("AIRUNNER_SITE_URL", "http://localhost:5173").strip().rstrip("/")

SMTP_CONFIGURED = bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)

# ── Template helpers ─────────────────────────────────────────────────

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _load_template(name: str) -> str:
    """Load a template file from the templates directory."""
    path = _TEMPLATES_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Email template not found: %s", path)
        return ""


# ── Core send function ───────────────────────────────────────────────


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str = "",
) -> bool:
    """Send an email via SMTP.

    Returns ``True`` on success, ``False`` on failure.
    Degrades gracefully when SMTP is not configured.
    """
    if not SMTP_CONFIGURED:
        logger.warning(
            "SMTP not configured — skipping email to %s (subject: %s). "
            "Set AIRUNNER_SMTP_HOST, AIRUNNER_SMTP_USER, and "
            "AIRUNNER_SMTP_PASSWORD to enable.",
            to_email,
            subject,
        )
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject

    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    if html_body:
        msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Email sent to %s (subject: %s)", to_email, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False


# ── Verification email ───────────────────────────────────────────────


def send_verification_email(to_email: str, username: str, token: str) -> bool:
    """Send an email verification link to *to_email*.

    The link points to ``{SITE_URL}/verify?token={token}``.
    """
    verify_url = f"{SITE_URL}/verify?token={token}"

    html_template = _load_template("verify_email.html")
    text_template = _load_template("verify_email.txt")

    context = {
        "username": username,
        "verify_url": verify_url,
        "site_url": SITE_URL,
    }

    html_body = Template(html_template).safe_substitute(context) if html_template else ""
    text_body = Template(text_template).safe_substitute(context) if text_template else ""

    subject = "Verify your email address"

    return send_email(to_email, subject, html_body, text_body)


# ── Password-reset email ─────────────────────────────────────────────


def send_password_reset_email(
    to_email: str, username: str, token: str,
) -> bool:
    """Send a password-reset link to *to_email*.

    The link points to ``{SITE_URL}/reset-password?token={token}``.
    """
    reset_url = f"{SITE_URL}/reset-password?token={token}"

    html_template = _load_template("password_reset.html")
    text_template = _load_template("password_reset.txt")

    context = {
        "username": username,
        "reset_url": reset_url,
        "site_url": SITE_URL,
    }

    html_body = (
        Template(html_template).safe_substitute(context)
        if html_template else ""
    )
    text_body = (
        Template(text_template).safe_substitute(context)
        if text_template else ""
    )

    subject = "Reset your password"

    return send_email(to_email, subject, html_body, text_body)


def send_waitlist_confirmation_email(to_email: str) -> bool:
    """Send a waitlist confirmation email to *to_email*."""
    subject = "You're on the waitlist"
    html_body = (
        "<p>You've been added to the waitlist.</p>"
        "<p>We'll send you an invitation when a spot opens up.</p>"
    )
    text_body = (
        "You've been added to the waitlist.\n\n"
        "We'll send you an invitation when a spot opens up.\n"
    )
    return send_email(to_email, subject, html_body, text_body)


__all__ = [
    "send_email",
    "send_password_reset_email",
    "send_verification_email",
    "send_waitlist_confirmation_email",
]
