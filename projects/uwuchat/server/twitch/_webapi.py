"""Twitch Helix API helpers — user profile and schedule endpoints."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_CLIENT_ID = os.environ.get("AIRUNNER_TWITCH_CLIENT_ID", "").strip()
_CLIENT_SECRET = os.environ.get("AIRUNNER_TWITCH_CLIENT_SECRET", "").strip()
_CONFIGURED = bool(_CLIENT_ID and _CLIENT_SECRET)


async def _get_app_token() -> str | None:
    """Obtain a Twitch app access token via client credentials."""
    if not _CONFIGURED:
        return None
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://id.twitch.tv/oauth2/token",
                data={
                    "client_id": _CLIENT_ID,
                    "client_secret": _CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("access_token")
    except Exception:
        logger.debug("Twitch app token fetch failed", exc_info=True)
        return None


async def get_user_info(
    twitch_id: str,
) -> dict[str, Any] | None:
    """Return user profile info for *twitch_id*, or ``None``."""
    if not _CONFIGURED:
        return None

    token = await _get_app_token()
    if token is None:
        return None

    import httpx

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://api.twitch.tv/helix/users",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Client-Id": _CLIENT_ID,
                },
                params={"id": twitch_id},
            )
            resp.raise_for_status()
            data = resp.json()
            users = data.get("data", [])
            if not users:
                return None
            return users[0]
    except Exception:
        logger.debug("Twitch get_user_info failed", exc_info=True)
        return None


async def get_channel_schedule(
    broadcaster_id: str,
) -> dict[str, Any] | None:
    """Fetch the channel schedule for *broadcaster_id*, or ``None``."""
    if not _CONFIGURED:
        return None

    token = await _get_app_token()
    if token is None:
        return None

    import httpx

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                "https://api.twitch.tv/helix/schedule",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Client-Id": _CLIENT_ID,
                },
                params={"broadcaster_id": broadcaster_id},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception:
        logger.debug("Twitch get_channel_schedule failed", exc_info=True)
        return None
