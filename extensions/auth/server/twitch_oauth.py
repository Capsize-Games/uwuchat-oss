"""Twitch OAuth 2.0 utilities for the auth extension.

Configuration (environment variables):
    AIRUNNER_TWITCH_CLIENT_ID       — Twitch application client ID
    AIRUNNER_TWITCH_CLIENT_SECRET   — Twitch application client secret
    AIRUNNER_SITE_URL               — Public-facing site URL for callback redirect

If Twitch OAuth is not configured (missing client ID/secret), the module
degrades gracefully — the Twitch sign-in button will not appear.
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

CLIENT_ID = os.environ.get("AIRUNNER_TWITCH_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get(
    "AIRUNNER_TWITCH_CLIENT_SECRET", "",
).strip()
SITE_URL = os.environ.get(
    "AIRUNNER_SITE_URL", "http://localhost:5173",
).strip().rstrip("/")

OAUTH_CONFIGURED = bool(CLIENT_ID and CLIENT_SECRET)

# Twitch OAuth endpoints
TWITCH_AUTH_URL = "https://id.twitch.tv/oauth2/authorize"
TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
TWITCH_VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"

# Scopes for login-only (email + profile)
LOGIN_SCOPES = [
    "user:read:email",
]

# Additional scopes for account linking (schedule access)
LINK_SCOPES = [
    "user:read:email",
]


# ── Types ────────────────────────────────────────────────────────────


class TwitchUserInfo:
    """Normalised user info returned from Twitch."""

    __slots__ = ("twitch_id", "email", "display_name", "avatar_url")

    def __init__(
        self,
        twitch_id: str,
        email: str,
        display_name: str,
        avatar_url: str,
    ) -> None:
        self.twitch_id = twitch_id
        self.email = email
        self.display_name = display_name
        self.avatar_url = avatar_url


# ── State management (reuses the same stateless JWT pattern) ─────────


def generate_state() -> str:
    """Generate a signed, short-lived CSRF state parameter."""
    from extensions.auth.server.jwt import create_oauth_state_token

    return create_oauth_state_token()


def consume_state(state: str) -> bool:
    """Validate a CSRF state parameter."""
    from extensions.auth.server.jwt import decode_token

    payload = decode_token(state, expected_type="oauth_state")
    return bool(payload)


# ── Client App access token (for Helix API calls) ───────────────────


async def _get_app_access_token() -> Optional[str]:
    """Obtain a Twitch app access token using client credentials.

    Required for Helix API calls that need a bearer token but aren't
    scoped to a specific user (e.g. fetching schedule data).
    """
    if not OAUTH_CONFIGURED:
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                TWITCH_TOKEN_URL,
                data={
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("access_token")
    except Exception:
        logger.exception("Failed to get Twitch app access token")
        return None


# ── URLs ─────────────────────────────────────────────────────────────


def get_twitch_auth_url(
    scopes: Optional[list[str]] = None,
) -> Optional[str]:
    """Return the Twitch OAuth consent URL, or ``None`` if not configured."""
    if not OAUTH_CONFIGURED:
        logger.warning(
            "Twitch OAuth not configured — set AIRUNNER_TWITCH_CLIENT_ID "
            "and AIRUNNER_TWITCH_CLIENT_SECRET to enable."
        )
        return None

    state = generate_state()
    redirect_uri = f"{SITE_URL}/api/v1/auth/oauth/twitch/callback"
    _scopes = scopes or LOGIN_SCOPES

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(_scopes),
        "state": state,
        "force_verify": "true",
    }

    return f"{TWITCH_AUTH_URL}?{urlencode(params)}"


def get_callback_uri() -> str:
    """Return the full callback URI this extension listens on."""
    return "/api/v1/auth/oauth/twitch/callback"


# ── Token exchange ───────────────────────────────────────────────────


async def exchange_code(code: str) -> Optional[TwitchUserInfo]:
    """Exchange an authorization code for user info from Twitch."""
    if not OAUTH_CONFIGURED:
        return None

    redirect_uri = f"{SITE_URL}/api/v1/auth/oauth/twitch/callback"

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
            token_resp = await client.post(
                TWITCH_TOKEN_URL, data=token_data,
            )
            token_resp.raise_for_status()
            tokens = token_resp.json()

            access_token = tokens.get("access_token")
            if not access_token:
                logger.error("Twitch OAuth: no access_token in response")
                return None

            # Validate token and get user id
            validate_resp = await client.get(
                TWITCH_VALIDATE_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )
            validate_resp.raise_for_status()
            validate_data = validate_resp.json()

            twitch_id = validate_data.get("user_id", "")
            login_name = validate_data.get("login", "")

            # Fetch full user profile from Helix
            user_resp = await client.get(
                TWITCH_USERS_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": CLIENT_ID,
                },
            )
            user_resp.raise_for_status()
            user_data = user_resp.json()
            users = user_data.get("data", [])
            if not users:
                logger.error("Twitch OAuth: no user data from Helix")
                return None

            user = users[0]
            email = user.get("email", "").strip().lower()
            display_name = user.get("display_name", login_name)
            avatar_url = user.get("profile_image_url", "")
            twitch_id = user.get("id", twitch_id)

            if not email:
                logger.error("Twitch OAuth: no email in Helix response")
                return None

            return TwitchUserInfo(
                twitch_id=twitch_id,
                email=email,
                display_name=display_name or email.split("@")[0],
                avatar_url=avatar_url,
            )

    except httpx.HTTPError as exc:
        logger.exception("Twitch OAuth HTTP error: %s", exc)
        return None
    except Exception:
        logger.exception("Twitch OAuth unexpected error")
        return None


# ── Helix API helpers (for schedule data) ────────────────────────────


async def get_channel_schedule(
    broadcaster_id: str,
) -> Optional[dict]:
    """Fetch the broadcaster's upcoming schedule from Twitch Helix.

    Returns the ``data`` portion of the Helix schedule response, or
    ``None`` on failure.  Requires a valid app access token.
    """
    if not OAUTH_CONFIGURED:
        return None

    token = await _get_app_access_token()
    if token is None:
        return None

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://api.twitch.tv/helix/schedule",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Client-Id": CLIENT_ID,
                },
                params={"broadcaster_id": broadcaster_id},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("data")
    except Exception:
        logger.exception(
            "Failed to fetch schedule for broadcaster=%s",
            broadcaster_id,
        )
        return None


async def get_user_by_id(
    twitch_id: str,
    access_token: str,
) -> Optional[dict]:
    """Get a Twitch user by ID using a user access token."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                TWITCH_USERS_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Client-Id": CLIENT_ID,
                },
                params={"id": twitch_id},
            )
            resp.raise_for_status()
            data = resp.json()
            users = data.get("data", [])
            return users[0] if users else None
    except Exception:
        logger.exception("Twitch get_user_by_id failed")
        return None


__all__ = [
    "OAUTH_CONFIGURED",
    "get_twitch_auth_url",
    "get_callback_uri",
    "exchange_code",
    "get_channel_schedule",
    "get_user_by_id",
    "TwitchUserInfo",
    "LOGIN_SCOPES",
    "LINK_SCOPES",
]
