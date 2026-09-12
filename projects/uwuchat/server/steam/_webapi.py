"""Steam Web API helpers — call GetPlayerSummaries & GetSteamLevel."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_STEAM_API_KEY = os.environ.get("STEAM_API_KEY", "").strip()
_BASE = "https://api.steampowered.com"


async def get_player_summaries(
    steam_id: str,
) -> dict[str, Any] | None:
    """Return the ``GetPlayerSummaries`` result for *steam_id*, or ``None``.

    Requires ``STEAM_API_KEY``.  Returns a dict with keys ``personaname``,
    ``avatar``, ``avatarmedium``, ``avatarfull``, ``profileurl``, etc.
    """
    if not _STEAM_API_KEY:
        logger.debug("STEAM_API_KEY not configured")
        return None

    import aiohttp

    url = (
        f"{_BASE}/ISteamUser/GetPlayerSummaries/v2/"
        f"?key={_STEAM_API_KEY}&steamids={steam_id}"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                data = await resp.json()
                players = data.get("response", {}).get("players", [])
                if not players:
                    return None
                return players[0]
    except Exception:
        logger.debug("GetPlayerSummaries failed", exc_info=True)
        return None


async def get_steam_level(steam_id: str) -> int | None:
    """Return the Steam level for *steam_id*, or ``None`` on failure.

    Requires ``STEAM_API_KEY``.
    """
    if not _STEAM_API_KEY:
        return None

    import aiohttp

    url = (
        f"{_BASE}/IPlayerService/GetSteamLevel/v1/"
        f"?key={_STEAM_API_KEY}&steamid={steam_id}"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("response", {}).get("player_level")
    except Exception:
        logger.debug("GetSteamLevel failed", exc_info=True)
        return None


def _build_game_entry(g: dict) -> dict[str, Any]:
    """Build a compact game dict from a raw Steam API game entry."""
    icon_hash = g.get("img_icon_url", "")
    return {
        "appid": g["appid"],
        "name": g.get("name", ""),
        "playtime_forever_minutes": g.get("playtime_forever", 0),
        "playtime_2weeks_minutes": g.get("playtime_2weeks"),
        "has_community_visible_stats": g.get(
            "has_community_visible_stats", False,
        ),
        "icon_url": (
            f"http://media.steampowered.com/"
            f"steamcommunity/public/images/apps/"
            f"{g['appid']}/{icon_hash}.jpg"
            if icon_hash
            else ""
        ),
    }


async def get_owned_games(
    steam_id: str,
) -> dict[str, Any] | None:
    """Return owned-games data or ``None``.

    Returns a dict with:
      - ``game_count`` (int)
      - ``total_playtime_minutes`` (int)
      - ``top_games`` (list of 5 most-played game dicts)
      - ``all_games`` (list of all game dicts, sorted by playtime)

    Requires ``STEAM_API_KEY`` and the user's game details to be public.
    """
    if not _STEAM_API_KEY:
        return None

    import aiohttp

    url = (
        f"{_BASE}/IPlayerService/GetOwnedGames/v1/"
        f"?key={_STEAM_API_KEY}&steamid={steam_id}"
        "&include_appinfo=1&include_played_free_games=1"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                games = data.get("response", {}).get("games", [])
                if not games:
                    return {
                        "game_count": 0,
                        "total_playtime_minutes": 0,
                        "top_games": [],
                        "all_games": [],
                    }
                games.sort(
                    key=lambda g: g.get("playtime_forever", 0),
                    reverse=True,
                )
                total_minutes = sum(
                    g.get("playtime_forever", 0) for g in games
                )
                all_entries = [_build_game_entry(g) for g in games]
                return {
                    "game_count": len(games),
                    "total_playtime_minutes": total_minutes,
                    "top_games": all_entries[:5],
                    "all_games": all_entries,
                }
    except Exception:
        logger.debug("GetOwnedGames failed", exc_info=True)
        return None


async def get_recently_played_games(
    steam_id: str,
) -> list[dict[str, Any]] | None:
    """Return recently played games (last 2 weeks) or ``None``.

    Each game dict has ``appid``, ``name``, ``playtime_forever_minutes``,
    ``playtime_2weeks_minutes``, ``icon_url``.

    Requires ``STEAM_API_KEY``.
    """
    if not _STEAM_API_KEY:
        return None

    import aiohttp

    url = (
        f"{_BASE}/IPlayerService/GetRecentlyPlayedGames/v1/"
        f"?key={_STEAM_API_KEY}&steamid={steam_id}"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                games = data.get("response", {}).get("games", [])
                return [_build_game_entry(g) for g in games]
    except Exception:
        logger.debug("GetRecentlyPlayedGames failed", exc_info=True)
        return None


async def get_friend_list(
    steam_id: str,
) -> int | None:
    """Return the number of friends, or ``None`` on failure.

    Requires ``STEAM_API_KEY`` and the user's friend list to be public.
    """
    if not _STEAM_API_KEY:
        return None

    import aiohttp

    url = (
        f"{_BASE}/ISteamUser/GetFriendList/v1/"
        f"?key={_STEAM_API_KEY}&steamid={steam_id}"
        "&relationship=friend"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                friends = data.get("friendslist", {}).get("friends", [])
                return len(friends)
    except Exception:
        logger.debug("GetFriendList failed", exc_info=True)
        return None


async def _get_achievement_schema(
    appid: int,
) -> dict[str, str]:
    """Return ``{apiname: icon_hash}`` for *appid*'s achievements.

    Calls ``ISteamUserStats/GetSchemaForGame/v2/`` which returns icon
    hashes for every achievement (unlike GetPlayerAchievements).
    """
    if not _STEAM_API_KEY:
        return {}

    import aiohttp

    url = (
        f"{_BASE}/ISteamUserStats/GetSchemaForGame/v2/"
        f"?key={_STEAM_API_KEY}&appid={appid}&l=en"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                achievements = (
                    data.get("game", {})
                    .get("availableGameStats", {})
                    .get("achievements", [])
                )
                icons: dict[str, str] = {}
                for ach in achievements:
                    name = ach.get("name", "")
                    icon = ach.get("icon", "")
                    icongray = ach.get("icongray", "")
                    if name:
                        icons[name] = icon
                        icons[name + "_gray"] = icongray
                return icons
    except Exception:
        logger.debug(
            "GetSchemaForGame failed", exc_info=True,
        )
        return {}


def _resolve_achievement_icon(raw: str, appid: int) -> str:
    """Build a CDN URL from a Steam achievement icon hash."""
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    base = (
        "http://media.steampowered.com/"
        "steamcommunity/public/images/apps/"
        f"{appid}/{raw}"
    )
    if any(raw.lower().endswith(e) for e in (".jpg", ".png", ".gif")):
        return base
    return base + ".jpg"


def _build_achievement_error(msg: str) -> dict[str, Any]:
    """Return an error-shaped achievements dict."""
    return {
        "error": msg,
        "achievements": [],
        "achieved_count": 0,
        "total_count": 0,
    }


async def _fetch_player_achievements_raw(
    steam_id: str, appid: int,
) -> dict[str, Any]:
    """Call GetPlayerAchievements and return the ``playerstats`` dict."""
    import aiohttp

    url = (
        f"{_BASE}/ISteamUserStats/GetPlayerAchievements/v1/"
        f"?key={_STEAM_API_KEY}&steamid={steam_id}&appid={appid}&l=en"
    )
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("playerstats", {})


def _enrich_achievements(
    achievements: list[dict[str, Any]],
    schema_icons: dict[str, str],
    pct_map: dict[str, float],
    appid: int,
) -> list[dict[str, Any]]:
    """Merge schema icons + global % into raw achievement dicts."""
    enriched: list[dict[str, Any]] = []
    for ach in achievements:
        apiname = ach.get("apiname", "")
        entry = {
            "apiname": apiname,
            "name": ach.get("name", ""),
            "description": ach.get("description", ""),
            "achieved": ach.get("achieved", 0) == 1,
            "unlocktime": ach.get("unlocktime", 0),
            "icon_url": _resolve_achievement_icon(
                schema_icons.get(apiname, ""), appid,
            ),
            "icon_gray_url": _resolve_achievement_icon(
                schema_icons.get(apiname + "_gray", ""), appid,
            ),
            "global_percent": pct_map.get(apiname),
        }
        enriched.append(entry)
    return enriched


async def _build_pct_map(appid: int) -> dict[str, float]:
    """Return ``{apiname: global_percent}`` for *appid*."""
    pcts = await _get_global_achievement_percentages(appid)
    if not pcts:
        return {}
    return {e["name"]: e["percent"] for e in pcts}


async def get_player_achievements(
    steam_id: str, appid: int,
) -> dict[str, Any]:
    """Return enriched achievements for *steam_id* in *appid*."""
    if not _STEAM_API_KEY:
        return _build_achievement_error(
            "STEAM_API_KEY not configured",
        )
    try:
        schema_icons = await _get_achievement_schema(appid)
        ps = await _fetch_player_achievements_raw(steam_id, appid)
        if not ps:
            return _build_achievement_error(
                "No player stats returned",
            )
        if not ps.get("success"):
            return _build_achievement_error(
                ps.get("error", "Profile is not public"),
            )
        pct_map = await _build_pct_map(appid)
        enriched = _enrich_achievements(
            ps.get("achievements", []),
            schema_icons, pct_map, appid,
        )
        return {
            "game_name": ps.get("gameName", ""),
            "appid": appid,
            "achievements": enriched,
            "achieved_count": sum(
                1 for a in enriched if a["achieved"]
            ),
            "total_count": len(enriched),
        }
    except Exception:
        logger.debug("GetPlayerAchievements failed", exc_info=True)
        return _build_achievement_error("Steam API request failed")


async def _get_global_achievement_percentages(
    appid: int,
) -> list[dict[str, Any]] | None:
    """Return global achievement percentages for *appid*, or ``None``.

    Calls ``ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/``.
    """
    if not _STEAM_API_KEY:
        return None

    import aiohttp

    url = (
        f"{_BASE}/ISteamUserStats/"
        f"GetGlobalAchievementPercentagesForApp/v2/"
        f"?gameid={appid}"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get(
                    "achievementpercentages", {},
                ).get("achievements", [])
    except Exception:
        logger.debug(
            "GetGlobalAchievementPercentagesForApp failed",
            exc_info=True,
        )
        return None
