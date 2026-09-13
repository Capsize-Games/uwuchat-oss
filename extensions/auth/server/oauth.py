"""Google OAuth 2.0 utilities for the auth extension.

Configuration (environment variables):
    AIRUNNER_GOOGLE_CLIENT_ID       — Google OAuth client ID
    AIRUNNER_GOOGLE_CLIENT_SECRET   — Google OAuth client secret
    AIRUNNER_SITE_URL               — Public-facing site URL for callback redirect

If Google OAuth is not configured (missing client ID/secret), the module
degrades gracefully — the Google sign-in button will not appear.
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

CLIENT_ID = os.environ.get("AIRUNNER_GOOGLE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("AIRUNNER_GOOGLE_CLIENT_SECRET", "").strip()
SITE_URL = os.environ.get("AIRUNNER_SITE_URL", "http://localhost:5173").strip().rstrip("/")

OAUTH_CONFIGURED = bool(CLIENT_ID and CLIENT_SECRET)

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Scopes
SCOPES = [
    "openid",
    "email",
    "profile",
]


# ── Types ────────────────────────────────────────────────────────────


class GoogleUserInfo:
    """Normalised user info returned from Google's userinfo endpoint."""

    __slots__ = ("google_id", "email", "name", "verified_email")

    def __init__(
        self,
        google_id: str,
        email: str,
        name: str,
        verified_email: bool,
    ) -> None:
        self.google_id = google_id
        self.email = email
        self.name = name
        self.verified_email = verified_email


# ── State management (stateless, signed; multi-worker safe) ──────────


def generate_state(extra: Optional[dict] = None) -> str:
    """Generate a signed, short-lived CSRF state parameter.

    Stateless: the state is a signed token that self-expires, so the flow
    works across multiple worker processes without shared storage and
    cannot grow memory over time. ``extra`` claims are merged into the
    token so they round-trip through the OAuth provider.
    """
    from extensions.auth.server.jwt import create_oauth_state_token

    return create_oauth_state_token(extra=extra)


def consume_state(state: str) -> bool:
    """Validate a CSRF state parameter.

    Returns ``True`` if the state is a valid, unexpired ``oauth_state``
    token, ``False`` otherwise.
    """
    from extensions.auth.server.jwt import decode_token

    payload = decode_token(state, expected_type="oauth_state")
    return bool(payload)


def decode_oauth_state(state: str) -> Optional[dict]:
    """Validate and decode a CSRF state parameter.

    Returns the full payload when the state is a valid, unexpired
    ``oauth_state``
    token, ``None`` otherwise.
    """
    from extensions.auth.server.jwt import decode_token

    payload = decode_token(state, expected_type="oauth_state")
    if payload:
        return payload
    return None


# ── URLs ─────────────────────────────────────────────────────────────


def get_google_auth_url() -> Optional[str]:
    """Return the Google OAuth consent URL, or ``None`` if not configured."""
    if not OAUTH_CONFIGURED:
        logger.warning(
            "Google OAuth not configured — set AIRUNNER_GOOGLE_CLIENT_ID "
            "and AIRUNNER_GOOGLE_CLIENT_SECRET to enable."
        )
        return None

    state = generate_state()
    redirect_uri = f"{SITE_URL}/api/v1/auth/oauth/google/callback"

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }

    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def get_callback_uri() -> str:
    """Return the full callback URI this extension listens on."""
    return f"/api/v1/auth/oauth/google/callback"


# ── Token exchange ───────────────────────────────────────────────────


async def exchange_code(code: str) -> Optional[GoogleUserInfo]:
    """Exchange an authorization code for user info from Google.

    Returns a ``GoogleUserInfo`` on success, or ``None`` on failure.
    """
    if not OAUTH_CONFIGURED:
        return None

    redirect_uri = f"{SITE_URL}/api/v1/auth/oauth/google/callback"

    token_data = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Exchange code for tokens
            token_resp = await client.post(GOOGLE_TOKEN_URL, data=token_data)
            token_resp.raise_for_status()
            tokens = token_resp.json()

            access_token = tokens.get("access_token")
            if not access_token:
                logger.error("Google OAuth: no access_token in response")
                return None

            # Fetch user info
            user_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_resp.raise_for_status()
            user_data = user_resp.json()

            google_id = user_data.get("id", "")
            email = user_data.get("email", "").strip().lower()
            name = user_data.get("name", "").strip()
            verified_email = user_data.get("verified_email", False)

            if not email:
                logger.error("Google OAuth: no email in userinfo response")
                return None

            return GoogleUserInfo(
                google_id=google_id,
                email=email,
                name=name or email.split("@")[0],
                verified_email=verified_email,
            )

    except httpx.HTTPError as exc:
        logger.exception("Google OAuth HTTP error: %s", exc)
        return None
    except Exception:
        logger.exception("Google OAuth unexpected error")
        return None


__all__ = [
    "OAUTH_CONFIGURED",
    "get_google_auth_url",
    "get_callback_uri",
    "exchange_code",
    "GoogleUserInfo",
]
