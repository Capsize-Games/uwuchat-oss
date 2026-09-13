"""itch.io API client — OAuth URL builder and JWT-authenticated fetches."""

from __future__ import annotations

import logging
import os
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

_CLIENT_ID = os.environ.get("ITCHIO_OAUTH_CLIENT_ID", "").strip()
_REDIRECT_URI = os.environ.get(
    "ITCHIO_OAUTH_REDIRECT_URI",
    os.environ.get("AIRUNNER_SITE_URL", "http://localhost:5173")
    .rstrip("/") + "/itch-callback.html",
).strip()
_OAUTH_URL = "https://itch.io/user/oauth"
_API_BASE = "https://itch.io/api/1"


def build_oauth_url(state: str) -> str:
    """Return the itch.io OAuth authorization URL with *state*."""
    params = {
        "client_id": _CLIENT_ID,
        "scope": "profile",
        "response_type": "token",
        "redirect_uri": _REDIRECT_URI,
        "state": state,
    }
    return f"{_OAUTH_URL}?{urlencode(params)}"


async def get_profile(token: str) -> dict[str, Any] | None:
    """Fetch user profile via JWT-authenticated /me."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{_API_BASE}/{token}/me",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                if "errors" in data:
                    logger.warning(
                        "itch.io /me returned errors: %s", data["errors"],
                    )
                    return None
                user = data.get("user")
                if user is None:
                    logger.warning(
                        "itch.io /me returned no user key: %s",
                        list(data.keys()) if data else "empty",
                    )
                return user
    except Exception:
        logger.warning("itch.io get_profile failed", exc_info=True)
        return None

async def get_owned_games(token: str) -> list[dict[str, Any]]:
    """Fetch owned games (purchases) via JWT /my-owned-keys."""
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{_API_BASE}/{token}/my-owned-keys",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                owned = data.get("owned_keys", [])
                games: list[dict[str, Any]] = []
                seen: set[int] = set()
                for key in owned:
                    game = key.get("game")
                    if game is None:
                        continue
                    gid = game.get("id")
                    if gid is None or gid in seen:
                        continue
                    seen.add(gid)
                    games.append({
                        "appid": f"itchio:{gid}",
                        "name": game.get("title", ""),
                        "playtime_forever_minutes": None,
                        "playtime_2weeks_minutes": None,
                        "icon_url": game.get("cover_url", "") or "",
                        "source": "itchio",
                        "source_url": game.get("url", "") or "",
                    })
                return games
    except Exception:
        logger.debug("itch.io get_owned_games failed", exc_info=True)
        return []
