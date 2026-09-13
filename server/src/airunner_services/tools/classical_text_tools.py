"""Classical text search tool — full-text lookup of public-domain books.

Calls the FastSearch /api/library/search-text/ endpoint and returns
attributed snippets in the same [SOURCE:...]/[END SOURCE] format used
by search_news in web_tools.py.
"""

import time
from typing import Annotated

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from airunner_services.llm.safety.search_rate_limiter import (
    check_search_rate_limit as _check_search_rate_limit,
)
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application.get_logger import get_logger
from airunner_services.utils.application.log_hygiene import (
    fingerprint_value,
    summarize_text,
)

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_last_classical_search_time = 0
_CLASSICAL_SEARCH_COOLDOWN = 2.0


def _respect_classical_cooldown(label: str) -> None:
    """Apply rate limiting between successive classical text searches."""
    global _last_classical_search_time
    time_since_last = time.time() - _last_classical_search_time
    if time_since_last < _CLASSICAL_SEARCH_COOLDOWN:
        wait_time = _CLASSICAL_SEARCH_COOLDOWN - time_since_last
        logger.info(
            "Rate limiting: waiting %.1fs before %s",
            wait_time,
            label,
        )
        time.sleep(wait_time)
    _last_classical_search_time = time.time()


@tool(
    name="search_classical_texts",
    category=ToolCategory.RESEARCH,
    description=(
        "Search the full text of public-domain classical books and "
        "literature (Project Gutenberg, Internet Archive). Returns "
        "attributed quotes and snippets with title, author, and "
        "chapter location. Use this for literary references, "
        "historical texts, philosophy, classic novels, poetry, "
        "and any pre-20th-century works."
    ),
    return_direct=False,
    requires_api=False,
)
def search_classical_texts(
    query: Annotated[
        str,
        "Search query for classical/public-domain texts — "
        "use quotes, concepts, or author names",
    ],
    max_results: Annotated[
        int,
        "Maximum number of results to return (default 5)",
    ] = 5,
) -> str:
    """Search public-domain classical texts via FastSearch."""
    import os
    import requests as _requests

    try:
        from airunner_services.llm.safety.account_context import (
            get_current_account_id,
        )

        account_id = get_current_account_id()
        if not _check_search_rate_limit(account_id):
            return (
                "Classical text search rate limit reached. "
                "Please wait a moment before making another "
                "search request."
            )
        _respect_classical_cooldown("classical text search")

        logger.info(
            "Searching classical texts (%s)",
            summarize_text(query, label="query"),
        )

        base_url = os.environ.get(
            "FASTSEARCH_BASE_URL", ""
        ).rstrip("/")
        api_key = os.environ.get("FASTSEARCH_API_KEY", "")
        if not base_url:
            logger.warning(
                "FASTSEARCH_BASE_URL not configured"
            )
            return {
                "results": [],
                "summary": (
                    "Classical text search is not configured. "
                    "The FastSearch service URL is not set."
                ),
            }

        headers = {"X-API-Key": api_key} if api_key else {}
        resp = _requests.get(
            f"{base_url}/api/library/search-text/",
            params={
                "q": query,
                "max_results": max(max_results, 1),
            },
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("results") or []

        logger.info("Got %d classical text results", len(raw))
        for _i, _r in enumerate(raw[:7], 1):
            logger.info(
                "  [%d] %s | %s",
                _i,
                (_r.get("author") or "?")[:30],
                (_r.get("title") or "")[:80],
            )

        if not raw:
            logger.info(
                "No classical text results for %r",
                fingerprint_value(query, label="query"),
            )
            return {
                "results": [],
                "summary": (
                    "No classical text results found for this "
                    "query. The texts may not cover this topic, "
                    "or the search service may be unavailable."
                ),
            }

        formatted = (
            f"Classical text results for '{query}':\n\n"
        )
        for i, result in enumerate(raw[:max_results], 1):
            title = result.get("title", "Unknown")
            author = result.get("author", "Unknown")
            snippet = (result.get("snippet") or "")[:400]
            book_id = result.get("book_id", "")
            chapter = result.get("chapter_or_location", "")

            formatted += f"{i}. [SOURCE: {title}"
            if author:
                formatted += f" by {author}"
            if chapter:
                formatted += f" — {chapter}"
            formatted += "]\n"
            if snippet:
                formatted += f"   \"{snippet}...\"\n"
            formatted += (
                f"   [END SOURCE] — book_id: {book_id}\n"
            )
            formatted += "\n"

        formatted += "\n" + "=" * 60 + "\n"
        formatted += "📝 NEXT STEPS: You can:\n"
        formatted += (
            "- Use `search_classical_texts` again with a "
            "different query\n"
        )
        formatted += (
            "- Quote these snippets with proper attribution\n"
        )
        formatted += (
            "- Or respond directly if you have enough "
            "information\n"
        )
        formatted += "=" * 60 + "\n"

        logger.info(
            "Formatted %d classical text results",
            len(raw[:max_results]),
        )
        return {"results": raw, "summary": formatted}

    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
            log_network_failure,
        )
        if is_transient_network_error(exc):
            log_network_failure(
                logger,
                "Classical text search error",
                exc,
            )
        else:
            logger.error(
                "Classical text search error: %s",
                exc,
                exc_info=True,
            )
        return f"Error searching classical texts: {str(exc)}"
