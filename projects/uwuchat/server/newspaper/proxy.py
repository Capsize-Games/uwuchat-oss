"""Proxy that fetches the FastSearch newspaper and caches it locally."""

from __future__ import annotations

import logging
import re
from typing import Optional

from projects.uwuchat.server.newspaper.cache import NewspaperCache

logger = logging.getLogger(__name__)

# Fallback: keep the per-turn snapshot under ~200 chars so it does not
# dominate the HumanMessage prefix.
_SNAPSHOT_MAX_LEN: int = 300


class NewspaperProxy:
    """Fetch the FastSearch-compiled newspaper and cache it locally.

    Uses :class:`NewspaperCache` for in-memory TTL storage and can
    extract compact snapshots suitable for per-turn context injection.
    """

    def __init__(self, fastsearch_provider) -> None:
        """Initialise the proxy.

        Args:
            fastsearch_provider: An instance of
                ``FastSearchProvider`` (or any object with a
                ``fetch_newspaper_markdown()`` async method).
        """
        self._provider = fastsearch_provider
        self._cache = NewspaperCache()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_newspaper(
        self,
        location: str | None = None,
        interests: str | None = None,
        force_refresh: bool = False,
    ) -> str:
        """Return cached or fresh newspaper as markdown.

        When *force_refresh* is ``False``, returns the cached copy if it
        is still within TTL.  Otherwise fetches from FastSearch.

        Args:
            location: Optional location string for weather
                (e.g. ``"Denver,CO"``).
            interests: Optional comma-separated interest tags.
            force_refresh: If ``True``, skip the cache and re-fetch.

        Returns:
            Markdown newspaper string.
        """
        cache_key = _cache_key(location, interests)

        if not force_refresh:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        markdown = await self._provider.fetch_newspaper_markdown(
            location=location,
            interests=interests,
        )

        self._cache.set(
            cache_key,
            markdown,
            snapshot=_extract_snapshot(markdown),
        )
        return markdown

    def get_compact_snapshot(
        self, key: str = "default"
    ) -> Optional[str]:
        """Return a compact summary of the cached newspaper for *key*.

        Suitable for per-turn context injection.  Returns ``None`` when
        no newspaper has been cached for the given key.

        Args:
            key: Cache key matching the one used in :meth:`get_newspaper`
                (defaults to ``"default"``).

        Returns:
            A short string like ``"🌤️ 72°F Denver | 📰 23 stories ..."``
            or ``None``.
        """
        return self._cache.get_snapshot(key)

    async def refresh(self, location: str | None = None) -> str:
        """Force-refresh and return the latest newspaper.

        Args:
            location: Optional location string.

        Returns:
            Fresh markdown newspaper.
        """
        return await self.get_newspaper(location=location, force_refresh=True)


# ------------------------------------------------------------------
# Module-level singleton (lazily initialised)
# ------------------------------------------------------------------

_proxy: Optional[NewspaperProxy] = None


def get_newspaper_proxy(fastsearch_provider=None) -> NewspaperProxy:
    """Return the module-level :class:`NewspaperProxy` singleton.

    On first call a *fastsearch_provider* must be supplied.

    Args:
        fastsearch_provider: A ``FastSearchProvider`` instance
            (required on the first call only).

    Returns:
        The singleton proxy.

    Raises:
        RuntimeError: If called for the first time without a provider.
    """
    global _proxy
    if _proxy is None:
        if fastsearch_provider is None:
            raise RuntimeError(
                "NewspaperProxy not initialised; pass fastsearch_provider "
                "on the first call."
            )
        _proxy = NewspaperProxy(fastsearch_provider)
    return _proxy


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _cache_key(location: str | None, interests: str | None) -> str:
    """Build a stable cache key from optional params."""
    parts = ["default"]
    if location:
        parts.append(f"loc={location.lower().replace(' ', '_')}")
    if interests:
        parts.append(f"int={interests.lower().replace(' ', '_')}")
    return ":".join(parts)


def _extract_snapshot(markdown: str) -> str:
    """Extract a compact snapshot from the full newspaper markdown.

    Captures:
    - Weather (first line of the weather section)
    - Story count
    - Up to 3 top headlines (title only)

    Args:
        markdown: Full newspaper markdown.

    Returns:
        Compact snapshot string (max ~300 chars).
    """
    parts: list[str] = []

    # Weather — look for the weather section header and next line
    weather_match = re.search(
        r"##\s*🌤️\s*Weather[^\n]*\n+([^\n#]+)", markdown
    )
    if weather_match:
        weather_line = weather_match.group(1).strip()
        if weather_line:
            parts.append(f"🌤️ {weather_line}")

    # Story count — count markdown links (approximation of article count)
    link_count = len(re.findall(r"\[([^\]]+)\]\(https?://[^)]+\)", markdown))
    if link_count:
        parts.append(f"📰 {link_count} stories")

    # Top headlines — grab up to 3 bold-linked titles
    headlines = re.findall(
        r"###\s*\[([^\]]+)\]\(https?://[^)]+\)", markdown
    )
    if headlines:
        top = " | ".join(f'"{h}"' for h in headlines[:3])
        parts.append(f"Top: {top}")

    snapshot = " · ".join(parts)
    if len(snapshot) > _SNAPSHOT_MAX_LEN:
        snapshot = snapshot[:_SNAPSHOT_MAX_LEN - 3] + "..."
    return snapshot
