"""FastSearch search provider — queries the FastSearch API.

Usage::

    provider = FastSearchProvider()
    results = await provider.search("machine learning", search_type="all")
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import aiohttp

from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.tools.search_providers.base_provider import (
    BaseSearchProvider,
)
from airunner_services.utils.application import get_logger


# ---------------------------------------------------------------------------
# Environment defaults
# ---------------------------------------------------------------------------
def _default_base_url() -> str:
    return os.environ.get("FASTSEARCH_BASE_URL", "http://127.0.0.1:8001")


def _default_api_key() -> str:
    return os.environ.get("FASTSEARCH_API_KEY", "")


class FastSearchProvider(BaseSearchProvider):
    """Search provider backed by the FastSearch custom search engine API.

    Attributes:
        base_url: Root URL of the FastSearch instance
            (default: ``$FASTSEARCH_BASE_URL`` or ``http://127.0.0.1:8001``).
        api_key: API key sent as ``X-API-Key`` header
            (default: ``$FASTSEARCH_API_KEY``).
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        super().__init__()
        self.base_url = (
            base_url.rstrip("/") if base_url else _default_base_url()
        )
        self.api_key = api_key if api_key is not None else _default_api_key()
        self._logger = get_logger(
            self.__class__.__name__, AIRUNNER_LOG_LEVEL
        )
        if not self.api_key:
            self._logger.warning(
                "FastSearchProvider initialized without an API key "
                "(FASTSEARCH_API_KEY is empty). All requests to %s "
                "will fail with 401 Unauthorized.",
                self.base_url,
            )

    # ------------------------------------------------------------------
    # Public API — matches BaseSearchProvider interface
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        search_type: str = "all",
        num_results: int = 10,
        client: aiohttp.ClientSession | None = None,
    ) -> List[Dict[str, str]]:
        """Unified search across all FastSearch content types.

        Args:
            query: Search query string.
            search_type: Content type filter.  One of ``"all"``,
                ``"pages"``, ``"images"``, ``"sites"``, ``"videos"``,
                ``"audio"``, ``"news"``, ``"books"``.
            num_results: Maximum number of results to return.
            client: Optional existing ``aiohttp.ClientSession``.

        Returns:
            List of formatted result dictionaries.
        """
        return await self._search(
            query=query,
            search_type=search_type,
            num_results=num_results,
            client=client,
        )

    # ------------------------------------------------------------------
    # Content-type-specific search methods
    # ------------------------------------------------------------------

    async def search_pages(
        self,
        query: str,
        num_results: int = 10,
        client: aiohttp.ClientSession | None = None,
    ) -> List[Dict[str, str]]:
        """Search for web pages / documents."""
        return await self._search(
            query=query,
            search_type="pages",
            num_results=num_results,
            client=client,
        )

    async def search_images(
        self,
        query: str,
        num_results: int = 10,
        client: aiohttp.ClientSession | None = None,
    ) -> List[Dict[str, str]]:
        """Search for images."""
        data = await self._request(
            "GET",
            "/api/images/",
            params={"q": query, "limit": num_results},
            client=client,
        )
        results = data.get("results", [])
        return [
            self._format_result(
                title=r.get("alt", r.get("ai_caption", "")),
                link=r.get("url", ""),
                snippet=r.get("ai_caption", ""),
            )
            for r in results
        ]

    async def search_news(
        self,
        query: str,
        num_results: int = 10,
        max_age_hours: int | None = None,
        country: str | None = None,
        client: aiohttp.ClientSession | None = None,
    ) -> List[Dict[str, str]]:
        """Search for news articles via the FastSearch news API.

        Uses ``GET /api/news/latest-summary/?q=<query>&limit=<n>`` which
        now tries the in-house RSS corpus first, falling back to
        NewsAPI.org and DuckDuckGo News, backed by a DB-level cache
        (30-min default TTL).

        Args:
            query: Free-text news search query (topical only, no dates).
            num_results: Maximum results to return.
            max_age_hours: If set, forwarded as a structured freshness
                parameter (NOT injected into the query string).
            country: Optional ISO 3166-1 alpha-2 country code for
                NewsAPI top-headlines fallback.
            client: Optional existing ``aiohttp.ClientSession``.
        """
        params: dict[str, Any] = {"q": query, "limit": num_results}
        if max_age_hours is not None:
            params["max_age_hours"] = max_age_hours
        if country is not None:
            params["country"] = country
        data = await self._request(
            "GET",
            "/api/news/latest-summary/",
            params=params,
            client=client,
        )
        results = data.get("results", [])
        return [
            self._format_result(
                title=r.get("title", ""),
                link=r.get("source_url", ""),
                snippet=r.get("summary", ""),
                source=r.get("source", ""),
                date=r.get("published_at", ""),
            )
            for r in results[:num_results]
        ]

    async def search_videos(
        self,
        query: str,
        num_results: int = 10,
        client: aiohttp.ClientSession | None = None,
    ) -> List[Dict[str, str]]:
        """Search for videos."""
        data = await self._request(
            "GET",
            "/api/videos/",
            params={"q": query, "limit": num_results},
            client=client,
        )
        results = data.get("results", [])
        return [
            self._format_result(
                title=r.get("title", ""),
                link=r.get("url", ""),
                snippet="",
            )
            for r in results
        ]

    async def search_audio(
        self,
        query: str,
        num_results: int = 10,
        client: aiohttp.ClientSession | None = None,
    ) -> List[Dict[str, str]]:
        """Search for audio."""
        data = await self._request(
            "GET",
            "/api/audios/",
            params={"q": query, "limit": num_results},
            client=client,
        )
        results = data.get("results", [])
        return [
            self._format_result(
                title=r.get("title", ""),
                link=r.get("url", ""),
                snippet="",
            )
            for r in results
        ]

    async def scrape_url(self, url: str) -> dict:
        """Fetch and clean a URL, returning plain text.

        Calls ``GET /api/scrape/?url=<url>`` on the FastSearch API.

        Returns:
            Dict with ``"url"``, ``"title"``, ``"content"``,
            ``"word_count"``, or ``"error"`` on failure.
        """
        try:
            data = await self._request(
                "GET",
                "/api/scrape/",
                params={"url": url},
            )
            return data
        except Exception as exc:
            return {"error": str(exc), "url": url}

    # ------------------------------------------------------------------
    # Newspaper
    # ------------------------------------------------------------------

    async def fetch_newspaper_markdown(
        self,
        location: str | None = None,
        interests: str | None = None,
        max_per_section: int = 10,
        client: aiohttp.ClientSession | None = None,
    ) -> str:
        """Fetch the compiled newspaper as markdown from FastSearch.

        Calls ``GET /api/newspaper/markdown/`` which returns a cached,
        compiled newspaper with all sections rendered as markdown.

        Args:
            location: Optional location for weather
                (e.g. ``"Denver,CO"``).
            interests: Optional comma-separated interest tags.
            max_per_section: Max items per section.
            client: Optional existing ``aiohttp.ClientSession``.

        Returns:
            Markdown string of the full newspaper.

        Raises:
            aiohttp.ClientError: On HTTP or network errors.
        """
        params: Dict[str, Any] = {"max_per_section": max_per_section}
        if location:
            params["location"] = location
        if interests:
            params["interests"] = interests
        data = await self._request(
            "GET",
            "/api/newspaper/markdown/",
            params=params,
            client=client,
        )
        return data.get("markdown", str(data))

    # ------------------------------------------------------------------
    # Topic brief
    # ------------------------------------------------------------------

    async def get_topic_brief(
        self,
        query: str,
        max_sources: int = 5,
        ttl: int = 7200,
        client: aiohttp.ClientSession | None = None,
    ) -> dict:
        """Fetch or generate a topic brief for a query.

        Calls ``GET /api/topic-brief/`` on the FastSearch API.

        Returns:
            Dict with ``"brief"`` (str|None), ``"sources"`` (list),
            ``"confidence"`` (str), and ``"cached"`` (bool).
        """
        try:
            return await self._request(
                "GET",
                "/api/topic-brief/",
                params={
                    "q": query,
                    "max_sources": max_sources,
                    "ttl": ttl,
                },
                client=client,
            )
        except Exception as exc:
            return {
                "brief": None,
                "sources": [],
                "confidence": "low",
                "cached": False,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def health(self) -> Dict[str, Any]:
        """Return connectivity status for the FastSearch API.

        Returns:
            Dict with ``"ok"`` (bool) and optionally ``"error"`` (str).
        """
        try:
            await self._request("GET", "/health/")
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _search(
        self,
        query: str,
        search_type: str = "all",
        num_results: int = 10,
        client: aiohttp.ClientSession | None = None,
    ) -> List[Dict[str, str]]:
        """Internal — unified search implementation."""
        data = await self._request(
            "GET",
            "/api/search/",
            params={"q": query, "type": search_type, "page": 1},
            client=client,
        )
        results = data.get("results", [])

        # FastSearch may return multiple result types; flatten and format
        formatted: List[Dict[str, str]] = []
        for r in results[:num_results]:
            rtype = r.get("type", "")
            if rtype == "page":
                formatted.append(
                    self._format_result(
                        title=r.get("title", ""),
                        link=r.get("url", ""),
                        snippet=r.get("snippet", ""),
                    )
                )
            elif rtype == "image":
                formatted.append(
                    self._format_result(
                        title=r.get("alt", r.get("ai_caption", "")),
                        link=r.get("url", ""),
                        snippet=r.get("ai_caption", ""),
                    )
                )
            elif rtype == "news":
                formatted.append(
                    self._format_result(
                        title=r.get("title", ""),
                        link=r.get("url", ""),
                        snippet=r.get("snippet", ""),
                        source=r.get("source", ""),
                        date=r.get("published_at", ""),
                    )
                )
            elif rtype == "web":
                formatted.append(
                    self._format_result(
                        title=r.get("title", ""),
                        link=r.get("url", ""),
                        snippet=r.get("snippet", ""),
                        source=r.get("source", ""),
                    )
                )
            else:
                # Fallback for unknown types
                formatted.append(
                    self._format_result(
                        title=r.get("title", r.get("alt", "")),
                        link=r.get("url", ""),
                        snippet=r.get("snippet", ""),
                    )
                )

        return formatted

    async def _request(
        self,
        method: str,
        path: str,
        params: Dict[str, Any] | None = None,
        json_body: Dict[str, Any] | None = None,
        client: aiohttp.ClientSession | None = None,
    ) -> Dict[str, Any]:
        """Perform an HTTP request to the FastSearch API.

        Args:
            method: HTTP method (``"GET"``, ``"POST"``, ``"PUT"``, etc.).
            path: URL path (e.g. ``/api/search/``).
            params: Optional query-string parameters.
            json_body: Optional JSON request body.
            client: Optional existing ``aiohttp.ClientSession``.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            aiohttp.ClientError: On HTTP or network errors.
        """
        url = f"{self.base_url}{path}"
        headers: Dict[str, str] = {"Accept": "application/json"}
        # X-Client-Account-Hash: non-reversible account identifier
        # for FastSearch-side correlation (P0.3).
        try:
            from airunner_services.llm.safety.account_context import (
                get_account_hash,
            )
            account_hash = get_account_hash()
            if account_hash:
                headers["X-Client-Account-Hash"] = account_hash
        except ImportError:
            pass
        if not self.api_key:
            self._logger.warning(
                "FastSearch API key is not configured (FASTSEARCH_API_KEY "
                "env var is empty). Requests to %s will fail with 401.",
                self.base_url,
            )
        else:
            headers["X-API-Key"] = self.api_key

        close_session = client is None
        if client is not None:
            session = client
        else:
            timeout = aiohttp.ClientTimeout(total=60.0)
            session = aiohttp.ClientSession(timeout=timeout)

        try:
            async with session.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=headers,
            ) as resp:
                if resp.status == 401:
                    body = await resp.text()
                    self._logger.error(
                        "FastSearch 401 Unauthorized for %s %s. "
                        "API key is %s. Response: %s",
                        method,
                        url,
                        "configured" if self.api_key else "MISSING",
                        body[:500],
                    )
                resp.raise_for_status()
                return await resp.json()
        finally:
            if close_session:
                await session.close()
