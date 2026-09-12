"""Bluesky App Password helpers.

Uses Bluesky's app password flow to create sessions and fetch posts.
Simpler than AT Protocol OAuth — no PAR, DPoP, or client metadata needed.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BSKY_API = "https://bsky.social"
_BSKY_PUBLIC_API = "https://public.api.bsky.app"


async def create_bsky_session(
    handle: str,
    app_password: str,
) -> dict[str, Any] | None:
    """Create a Bluesky session using handle + app password.

    Returns dict with did, handle, accessJwt, refreshJwt on success,
    or None on failure.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_BSKY_API}/xrpc/com.atproto.server.createSession",
                json={
                    "identifier": handle.strip(),
                    "password": app_password.strip(),
                },
            )
            if resp.status_code != 200:
                logger.warning(
                    "Bluesky createSession failed: %s %s",
                    resp.status_code,
                    resp.text[:200],
                )
                return None
            data = resp.json()
            return {
                "did": data.get("did", ""),
                "handle": data.get("handle", handle.strip()),
                "access_jwt": data.get("accessJwt", ""),
                "refresh_jwt": data.get("refreshJwt", ""),
            }
    except Exception as exc:
        logger.error("Bluesky session creation error: %s", exc)
        return None


async def fetch_author_feed(handle: str) -> list[dict[str, Any]]:
    """Fetch recent posts for a Bluesky handle using the public API."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_BSKY_PUBLIC_API}/xrpc/app.bsky.feed.getAuthorFeed",
                params={"actor": handle.strip(), "limit": 5},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            raw = data.get("feed", [])
            posts = []
            for item in raw:
                post = item.get("post", {})
                record = post.get("record", {})
                embed = post.get("embed")
                posts.append({
                    "uri": post.get("uri", ""),
                    "cid": post.get("cid", ""),
                    "text": record.get("text", ""),
                    "createdAt": record.get("createdAt", ""),
                    "likeCount": post.get("likeCount", 0),
                    "repostCount": post.get("repostCount", 0),
                    "replyCount": post.get("replyCount", 0),
                    "embed": (
                        {
                            "$type": embed.get("$type"),
                            "images": [
                                {
                                    "thumb": img.get("thumb", ""),
                                    "fullsize": img.get("fullsize", ""),
                                    "alt": img.get("alt", ""),
                                }
                                for img in embed.get("images", [])
                            ]
                            if embed.get("images")
                            else [],
                        }
                        if embed
                        else None
                    ),
                })
            return posts
    except Exception as exc:
        logger.warning("Bluesky posts fetch failed: %s", exc)
        return []
