"""Web search and scraping tools."""

import time
from typing import Annotated

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from airunner_services.settings import AIRUNNER_LOG_LEVEL

from airunner_services.utils.application.get_logger import get_logger
from airunner_services.utils.application.log_hygiene import (
    fingerprint_value,
    summarize_text,
)

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_last_search_time = 0
_SEARCH_COOLDOWN = 2.0

# Per-account rate limiter for search/scrape tool calls.
# Default: 10 calls per 60-second window per account.
# Configured in airunner_services.llm.safety.search_rate_limiter.
from airunner_services.llm.safety.search_rate_limiter import (
    check_search_rate_limit as _check_search_rate_limit,
)


def _respect_search_cooldown(search_label: str) -> None:
    """Apply rate limiting between successive internet tool requests."""
    global _last_search_time
    time_since_last = time.time() - _last_search_time
    if time_since_last < _SEARCH_COOLDOWN:
        wait_time = _SEARCH_COOLDOWN - time_since_last
        logger.info(
            "Rate limiting: waiting %.1fs before %s",
            wait_time,
            search_label,
        )
        time.sleep(wait_time)
    _last_search_time = time.time()



def _fastsearch_results(
    query: str,
    search_type: str = "all",
    num_results: int = 10,
) -> list[dict]:
    """Query the FastSearch API for the given search type.

    News queries are routed to ``/api/news/latest-summary/``
    (NewsAPI.org + DuckDuckGo News, DB-cached).  All other types
    use the unified ``/api/search/`` endpoint.

    Returns an empty list on any failure so callers can fall back
    gracefully.
    """
    import os
    import requests as _requests

    base_url = os.environ.get("FASTSEARCH_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("FASTSEARCH_API_KEY", "")
    if not base_url:
        return []
    headers = {"X-API-Key": api_key} if api_key else {}
    try:
        if search_type == "news":
            resp = _requests.get(
                f"{base_url}/api/news/latest-summary/",
                params={
                    "q": query,
                    "limit": num_results,
                    "scrape": "true",
                    "scrape_limit": 3,
                    "max_age_hours": 12,
                },
                headers=headers,
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("results") or []
            out = []
            for r in raw[:num_results]:
                entry = {
                    "title": r.get("title", ""),
                    "link": r.get("source_url", ""),
                    "snippet": r.get("summary", ""),
                    "source": r.get("source", ""),
                    "date": r.get("published_at", ""),
                }
                content_summary = r.get("content_summary")
                if content_summary:
                    entry["content"] = content_summary
                    entry["is_scraped"] = r.get("is_scraped", True)
                else:
                    content = r.get("content")
                    if content:
                        entry["content"] = content[:500]
                        entry["is_scraped"] = r.get(
                            "is_scraped", bool(content)
                        )
                out.append(entry)
            return out

        resp = _requests.get(
            f"{base_url}/api/search/",
            params={"q": query, "type": search_type, "page": 1},
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data.get("results") or []
        out = []
        for r in raw[:num_results]:
            out.append({
                "title": r.get("title", ""),
                "link": r.get("url", ""),
                "snippet": r.get("snippet") or r.get("description") or "",
                "source": r.get("source") or r.get("source_name") or "",
                "date": r.get("published_at") or r.get("date") or "",
            })
        return out
    except Exception as exc:
        logger.debug("FastSearch query (type=%s) failed: %s", search_type, exc)
        return []



def _fastsearch_news_search(
    query: str, num_results: int = 10
) -> list[dict]:
    """Return news results from FastSearch (latest-summary then news/search)."""
    results = _fastsearch_results(
        query, search_type="news", num_results=num_results
    )
    if results:
        return results
    try:
        import os
        import requests as _requests

        base_url = os.environ.get("FASTSEARCH_BASE_URL", "").rstrip("/")
        api_key = os.environ.get("FASTSEARCH_API_KEY", "")
        if not base_url:
            return []
        headers = {"X-API-Key": api_key} if api_key else {}
        resp = _requests.get(
            f"{base_url}/api/news/search/",
            params={"q": query, "limit": num_results},
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("results") or []
        return [
            {
                "title": r.get("title", ""),
                "link": r.get("url", ""),
                "snippet": r.get("description", ""),
                "source": r.get("source", ""),
                "date": r.get("published_at", ""),
            }
            for r in raw[:num_results]
        ]
    except Exception as exc:
        logger.debug("FastSearch news/search failed: %s", exc)
        return []


def _news_results(query: str, num_results: int = 10) -> list[dict]:
    """Return combined news + web results for *query* via FastSearch only.

    News articles come first (FastSearch news endpoints).  General web
    results from the FastSearch search API are always appended so that
    queries with sparse news coverage still return useful content.
    Results are deduplicated by URL.
    """
    news = _fastsearch_news_search(query, num_results=num_results)
    if news:
        logger.info("News search returned %d results", len(news))
    else:
        logger.info(
            "FastSearch news returned no results for %r",
            query[:80],
        )

    web = _fastsearch_results(
        query, search_type="all", num_results=num_results
    )
    if web:
        logger.info("Web search returned %d results", len(web))
    else:
        logger.info(
            "FastSearch web search returned no results for %r",
            query[:80],
        )

    seen: set[str] = {r.get("link", "") for r in news if r.get("link")}
    combined = list(news)
    for r in web:
        url = r.get("link", "")
        if url and url not in seen:
            combined.append(r)
            seen.add(url)

    return combined[: num_results * 2]


# LAUNCH DISABLED: search_web is not registered at soft launch.
# Retrieve tools cause DeepSeek 400 errors on tool-continuation turns because
# their ToolMessage results cannot be stripped (unlike write-only tools).
# Re-enable once the two-phase tool architecture is implemented.
# See wiki/planned_work/two-phase-tool-architecture.md
# @tool(
#     name="search_web",
#     category=ToolCategory.SEARCH,
#     description=(...),
#     defer_loading=False,
#     keywords=["internet", "google", "duckduckgo", "online", "web", "find"],
# )
def search_web(
    query: Annotated[str, "Search query to look up on the internet"],
) -> str:
    """Search the internet for information via FastSearch."""
    try:
        from airunner_services.llm.safety.account_context import (
            get_current_account_id,
        )

        account_id = get_current_account_id()
        if not _check_search_rate_limit(account_id):
            return (
                "Search rate limit reached. Please wait a moment "
                "before making another search request."
            )
        _respect_search_cooldown("search")

        logger.info(
            "Searching web (%s)",
            summarize_text(query, label="query"),
        )

        results = _fastsearch_results(
            query, search_type="all", num_results=10
        )
        logger.info("Got %d web results", len(results))

        if not results:
            logger.warning("Empty web results list")
            return "No web results found for this query."

        formatted = f"Web search results for '{query}':\n\n"
        for i, result in enumerate(results[:5], 1):
            title = result.get("title", "N/A")
            link = result.get("link", "#")
            snippet = (result.get("snippet") or "")[:200]
            formatted += f"{i}. {title}\n"
            formatted += f"   URL: {link}\n"
            if snippet:
                formatted += f"   {snippet}...\n"
            formatted += "\n"

        formatted += "\n" + "=" * 60 + "\n"
        formatted += "📝 NEXT STEPS: You can:\n"
        formatted += (
            "- Use `scrape_website` on a URL to get full article content\n"
        )
        formatted += (
            "- Use `search_web` again with a different query for more info\n"
        )
        formatted += "- Or respond directly if you have enough information\n"
        formatted += "=" * 60 + "\n"

        logger.info("Formatted %d search results", len(results[:5]))
        return formatted
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
            log_network_failure,
        )
        if is_transient_network_error(exc):
            log_network_failure(logger, "Web search error", exc)
        else:
            logger.error("Web search error: %s", exc, exc_info=True)
        return f"Error searching web: {str(exc)}"


@tool(
    name="search_news",
    category=ToolCategory.SEARCH,
    description=(
        "Search for recent news articles and current events using "
        "FastSearch (supplemented by web search when news coverage is "
        "sparse). Returns results with titles, URLs, snippets, sources, "
        "and dates. ALWAYS use this for current events, recent decisions, "
        "breaking news, or anything time-sensitive. Better than search_web "
        "for: politics, government actions, recent appointments, etc."
    ),
    return_direct=False,
    requires_api=False,
)
def search_news(
    query: Annotated[
        str,
        "News search query — strip dates and years (freshness is "
        "automatic) but KEEP event-type nouns (\"speech\", "
        "\"eulogy\", \"announcement\", \"debate\") that identify "
        "a specific occurrence. e.g. \"policy speech reaction\" "
        "not bare \"news\".",
    ],
) -> str:
    """Search for recent news articles via FastSearch."""

    try:
        from airunner_services.llm.safety.account_context import (
            get_current_account_id,
        )

        account_id = get_current_account_id()
        if not _check_search_rate_limit(account_id):
            return (
                "News search rate limit reached. Please wait a moment "
                "before making another search request."
            )
        _respect_search_cooldown("news search")

        logger.info(
            "Searching news (%s)",
            summarize_text(query, label="query"),
        )

        results = _news_results(query, num_results=10)

        logger.info("Got %d news results", len(results))
        for _i, _r in enumerate(results[:7], 1):
            logger.info(
                "  [%d] %s | %s | %s",
                _i,
                (_r.get("date") or "no-date")[:10],
                (_r.get("source") or "?")[:20],
                (_r.get("title") or "")[:80],
            )

        if not results:
            logger.warning("No news results returned")
            return (
                "No news results found for this query. "
                "The news search service is currently unavailable "
                "or rate-limited. Please inform the user and do not "
                "retry the search."
            )

        formatted = f"Recent news articles for '{query}':\n\n"
        for i, result in enumerate(results[:7], 1):
            title = result.get("title", "N/A")
            link = result.get("link", "#")
            snippet = (result.get("snippet") or "")[:250]
            source = result.get("source", "Unknown source")
            date = result.get("date", "")

            formatted += f"{i}. [SOURCE: {title}"
            if date:
                formatted += f" | {date}"
            formatted += "]\n"
            if snippet:
                formatted += f"   {snippet}...\n"
            formatted += f"   [END SOURCE] — URL: {link} | {source}\n"
            formatted += "\n"

        formatted += "\n" + "=" * 60 + "\n"
        formatted += "📝 NEXT STEPS: You can:\n"
        formatted += (
            "- Use `scrape_website` on a URL to get full article content\n"
        )
        formatted += (
            "- Use `search_news` again with a different query for more info\n"
        )
        formatted += "- Or respond directly if you have enough information\n"
        formatted += "=" * 60 + "\n"

        logger.info("Formatted %d news results", len(results[:7]))
        return formatted
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
            log_network_failure,
        )
        if is_transient_network_error(exc):
            log_network_failure(logger, "News search error", exc)
        else:
            logger.error("News search error: %s", exc, exc_info=True)
        return f"Error searching news: {str(exc)}"


@tool(
    name="scrape_website",
    category=ToolCategory.SEARCH,
    description=(
        "Scrape and extract clean text content from a website URL. "
        "Automatically removes boilerplate, navigation, ads, and footer "
        "elements. Returns only the main content of the page. Use this to "
        "read articles, blog posts, documentation, or any web page content."
    ),
    return_direct=False,
    requires_api=False,
)
def scrape_website(
    url: Annotated[
        str,
        "Website URL to scrape content from (must include http:// or https://)",
    ],
) -> dict:
    """Scrape and extract clean content with metadata from a website."""
    from airunner_services.llm.safety.account_context import (
        get_current_account_id,
    )

    account_id = get_current_account_id()
    if not _check_search_rate_limit(account_id):
        return {
            "content": None,
            "error": (
                "Scrape rate limit reached. Please wait a moment "
                "before making another scrape request."
            ),
        }
    logger.info(
        "Scraping website (%s)",
        fingerprint_value(url, label="url"),
    )

    try:
        from airunner_services.tools.web_content_extractor import (
            WebContentExtractor,
        )

        result = WebContentExtractor.fetch_and_extract_with_metadata(
            url,
            use_cache=True,
        )

        if result and result.get("content"):
            content = result["content"]
            # Truncate to 8 KB to limit context-window amplification.
            content = content[:8192]
            # Scan for prompt-injection patterns in scraped content.
            from airunner_services.llm.safety.content_injection_scan import (
                scan_and_log_injection,
            )
            from urllib.parse import urlparse

            host = urlparse(url).hostname or "unknown"
            content, _ = scan_and_log_injection(
                content,
                source_label=f"scrape_website:{host}",
                account_id=account_id,
            )
            result["content"] = content
            logger.info(
                "Extracted %d characters from scraped website",
                len(content),
            )
            logger.info("Title: %s", result.get("title", "N/A"))
            result["_instructions"] = (
                "📝 IMPORTANT: Use this content to answer the user's "
                "original question. Optionally, use record_knowledge() "
                "to save key facts for future reference."
            )
            return result

        return {
            "content": None,
            "error": (
                f"Could not extract content from {url}. The page may be "
                "empty, require JavaScript, or be blocking scrapers."
            ),
        }
    except Exception as exc:
        logger.error(
            "Web scraping error (%s): %s",
            fingerprint_value(url, label="url"),
            exc,
            exc_info=True,
        )
        return {"content": None, "error": f"Error scraping {url}: {str(exc)}"}
