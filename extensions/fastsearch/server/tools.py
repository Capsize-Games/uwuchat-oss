"""LLM tool functions backed by the FastSearch API.

These tools are registered with ``ToolRegistry`` via the ``@tool``
decorator when the module is imported.  The import is triggered by
:meth:`FastSearchExtension.ready` in ``config.py``.
"""

from __future__ import annotations

import os
import re

from typing import Annotated, Any, Callable, Coroutine

from airunner_services.llm.core.tool_registry import ToolCategory, tool

# Regex for defensive query sanitization: strips trailing ISO dates
# and "today <Month> <Day>,? <Year>" patterns from the tail of a
# free-text news query.  Tail-anchored to avoid mangling legitimate
# query text that might happen to contain a date-like string in the
# middle.  This is a safety net, not a general NLP date parser.
_TAIL_DATE_RE = re.compile(
    r"\s+("
    r"\d{4}-\d{2}-\d{2}"  # ISO: 2026-07-06
    r"|today\s+\w+\s+\d{1,2},?\s*\d{4}"  # "today July 6, 2026"
    r"|today\s+\w+\s+\d{1,2}"  # "today July 6" (no year)
    r"|today\s+\d{4}"  # "today 2026"
    r")\s*$",
    re.IGNORECASE,
)
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application.get_logger import get_logger

from extensions.fastsearch.server.provider import FastSearchProvider
from extensions.fastsearch.server.search_result_capping import (
    cap_query_blocks,
)

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

# Maximum characters for a compiled topic brief before truncation.
# Configurable via FASTSEARCH_TOPIC_BRIEF_MAX_CHARS; default 8 000
# chars (~2 000 tokens) keeps the brief informative without blowing
# up the DIALOGUE input context window.
_TOPIC_BRIEF_MAX_CHARS = int(
    os.getenv("FASTSEARCH_TOPIC_BRIEF_MAX_CHARS", "8000")
)

# Maximum number of queries in a single search_fastsearch or
# search_fastsearch_news call.  Configurable via env var; default 5
# balances broad coverage against per-turn cost and rate-limiting.
# Excess queries are truncated with a note — never silently dropped
# and never errored.
_MAX_QUERIES_PER_CALL = int(
    os.getenv("FASTSEARCH_MAX_QUERIES_PER_CALL", "5")
)


def _truncate_queries(queries: list[str], func_name: str) -> list[str]:
    """Cap *queries* at ``_MAX_QUERIES_PER_CALL`` and return the
    truncated list.  If any queries were dropped, a synthetic query
    is appended with a brief note so the caller knows the batch was
    clipped — never silently dropped, never errored.

    The note text is deliberately neutral (no "dropped", "capped",
    or "limit" language) so the model won't narrate it back to the
    user as a system complaint.
    """
    if len(queries) <= _MAX_QUERIES_PER_CALL:
        return queries
    dropped = queries[_MAX_QUERIES_PER_CALL:]
    note = (
        f"[{func_name}: searched the first {_MAX_QUERIES_PER_CALL} "
        f"quer{'y' if len(dropped) == 1 else 'ies'} "
        f"out of {len(queries)} requested]"
    )
    return list(queries[:_MAX_QUERIES_PER_CALL]) + [note]


def _find_truncation_boundary(truncated: str, max_chars: int) -> int:
    """Return the best clean-cut boundary index within *truncated*."""
    para_break = truncated.rfind("\n\n")
    if para_break > max_chars * 0.5:
        return para_break

    sentence_break = max(
        truncated.rfind(". "),
        truncated.rfind("! "),
        truncated.rfind("? "),
    )
    if sentence_break > max_chars * 0.3:
        return sentence_break + 1

    word_break = truncated.rfind(" ")
    if word_break > 0:
        return word_break

    return max_chars


def _format_truncation_note(used_chars: int, total_chars: int) -> str:
    """Return a markdown note indicating the brief was truncated."""
    return (
        "\n\n---\n"
        "*[Topic brief truncated at {chars:,} characters. "
        "The full brief was {total:,} characters.]*"
    ).format(chars=used_chars, total=total_chars)


def _truncate_brief(brief: str, max_chars: int) -> str:
    """Truncate *brief* to at most *max_chars* at a clean boundary.

    Prefers paragraph breaks, falls back to sentence breaks, then
    word boundaries.  Appends a short truncation note so the model
    knows the brief was cut.
    """
    if len(brief) <= max_chars:
        return brief

    boundary = _find_truncation_boundary(brief[:max_chars], max_chars)
    return brief[:boundary].rstrip() + _format_truncation_note(
        boundary, len(brief)
    )


def _run_async(coro):
    """Safely run an async coroutine from synchronous tool code.

    Uses ``asyncio.run()`` when no event loop is active.  When called
    from inside a running event loop (e.g. FastAPI handler thread or
    QThread with its own loop), spawns a fresh thread to avoid
    ``RuntimeError: asyncio.run() cannot be called from a running
    event loop``.

    Args:
        coro: The coroutine to execute.

    Returns:
        The coroutine's return value.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — asyncio.run() is safe.
        return asyncio.run(coro)

    # A loop is already running — run the coroutine in a fresh thread.
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _get_provider() -> FastSearchProvider:
    """Return a ``FastSearchProvider`` using current environment config."""
    return FastSearchProvider()


# ------------------------------------------------------------------
# Concurrent query execution (bounded concurrency + retry)
# ------------------------------------------------------------------


async def _execute_concurrent_queries(
    queries: list[str],
    do_query: "Callable[[str, aiohttp.ClientSession], Coroutine[Any, Any, list[dict]]]",
) -> list[tuple[str, object]]:
    """Run *do_query(q, session)* for each query concurrently.

    Concurrency is bounded by ``CONCURRENCY_LIMIT``.  Each query
    gets one retry on HTTP 502/503/504.  All queries share a single
    ``aiohttp.ClientSession`` for connection reuse.

    Returns a list of ``(query, result_or_exception)`` in the same
    order as *queries*.
    """
    import asyncio

    import aiohttp
    from extensions.fastsearch.server.concurrent_search import (
        CONCURRENCY_LIMIT,
        retry_call,
    )

    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    timeout = aiohttp.ClientTimeout(total=90.0)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY_LIMIT + 1)

    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
    ) as session:

        async def _one(query: str) -> object:
            async with semaphore:
                return await retry_call(
                    lambda: do_query(query, session),
                    query_label=query,
                )

        gathered = await asyncio.gather(
            *[_one(q) for q in queries],
            return_exceptions=True,
        )

    return list(zip(queries, gathered))


def _process_search_results(
    raw_results: list[tuple[str, object]],
    search_type: str,
    tool_name: str,
) -> tuple[list[dict], list[str]]:
    """Iterate *raw_results*, formatting successes and failures.

    Returns ``(per_query_results, formatted_parts)`` suitable for
    ``cap_query_blocks``.
    """
    per_query_results: list[dict] = []
    formatted_parts: list[str] = []

    for query, result in raw_results:
        if isinstance(result, BaseException):
            logger.error(
                "%s error (%s): %s",
                tool_name,
                query[:80],
                result,
                exc_info=True,
            )
            per_query_results.append({
                "query": query,
                "results": [],
            })
            formatted_parts.append(
                f"FastSearch search failed for '{query}': {result}"
            )
            continue

        results: list[dict] = result  # type: ignore[assignment]
        if not results:
            logger.warning(
                "%s returned no results for query '%s'",
                tool_name,
                query[:80],
            )
            per_query_results.append({
                "query": query,
                "results": [],
            })
            formatted_parts.append(
                f"No results found for '{query}'. "
                "Try a different query or content type."
            )
            continue

        formatted = _format_results(query, results, search_type)
        formatted = _scan_tool_output(
            formatted, f"{tool_name}:{query[:50]}"
        )
        per_query_results.append({
            "query": query,
            "results": results,
        })
        formatted_parts.append(formatted)

    return per_query_results, formatted_parts


def _process_news_results(
    raw_results: list[tuple[str, object]],
    originals: list[str],
    num_results: int,
) -> tuple[list[dict], list[str]]:
    """Iterate *raw_results* from concurrent news search, formatting
    successes and mapping sanitized queries back to original labels.

    *originals* is the list of original (pre-sanitized) query strings
    in the same positional order as *raw_results*.  Positional lookup
    avoids dict-key collisions when two original queries sanitize to
    the same string.

    Returns ``(per_query_results, formatted_parts)``.
    """
    per_query_results: list[dict] = []
    formatted_parts: list[str] = []

    for idx, (sanitized, result) in enumerate(raw_results):
        original = originals[idx] if idx < len(originals) else sanitized
        if isinstance(result, BaseException):
            logger.error(
                "search_fastsearch_news error (%s): %s",
                original[:80],
                result,
                exc_info=True,
            )
            per_query_results.append({
                "query": original,
                "results": [],
            })
            formatted_parts.append(
                f"FastSearch news search failed for "
                f"'{original}': {result}"
            )
            continue

        results: list[dict] = result  # type: ignore[assignment]
        if not results:
            logger.warning(
                "FastSearch news returned no results for '%s'",
                original[:80],
            )
            per_query_results.append({
                "query": original,
                "results": [],
            })
            formatted_parts.append(
                f"No news articles found for '{original}'. "
                "Try a different query."
            )
            continue

        formatted = (
            f"Recent news articles for '{original}':\n\n"
        )
        for i, r in enumerate(results[:num_results], 1):
            title = r.get("title", "N/A")
            source = r.get("source", "Unknown source")
            date = r.get("date", "")
            link = r.get("link", "#")
            snippet = _strip_html(
                (r.get("snippet", "") or "")
            )[:250]

            formatted += f"{i}. {title}\n"
            formatted += f"   Source: {source}"
            if date:
                formatted += f" | Date: {date}"
            formatted += f"\n   URL: {link}\n"
            if snippet:
                formatted += f"   {snippet}...\n"
            formatted += "\n"

        formatted = _scan_tool_output(
            formatted,
            f"search_fastsearch_news:{original[:50]}",
        )
        per_query_results.append({
            "query": original,
            "results": results,
        })
        formatted_parts.append(formatted)

    return per_query_results, formatted_parts


# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------


@tool(
    name="search_fastsearch",
    category=ToolCategory.RESEARCH,
    description=(
        "Search the web using FastSearch — a custom search engine that "
        "indexes web pages, images, videos, news, audio, and books. "
        "Use this as an alternative to search_web when DuckDuckGo is "
        "blocked or unavailable. "
        "Defaults to 'pages' (text/article results) for general "
        "research. Use search_type='all' for multi-type results, "
        "or 'images'/'news'/'books' for specific content. "
        "Pass every distinct query you need this turn as one list in a "
        "single call — do not call this tool multiple times in the same turn."
    ),
    return_direct=False,
    requires_api=True,
    defer_loading=True,
    keywords=[
        "fastsearch",
        "search",
        "web",
        "internet",
        "find",
        "research",
        "images",
        "news",
        "videos",
        "custom search",
    ],
    input_examples=[
        {
            "queries": ["Python programming tutorials"],
            "search_type": "all",
        },
        {
            "queries": [
                "latest climate research papers",
                "renewable energy breakthroughs",
            ],
            "search_type": "pages",
        },
    ],
)
def search_fastsearch(
    queries: Annotated[
        list[str],
        "One or more search queries to look up on the web. "
        "Pass every distinct query you need this turn as one list "
        "in a single call — do not call this tool multiple times "
        "in the same turn.",
    ],
    search_type: Annotated[
        str,
        (
            "Content type to search. One of: 'pages' (default), "
            "'all', 'images', 'news', 'books'. "
            "Use 'pages' for text/article research, "
            "'all' to also get images/video/audio results."
        ),
    ] = "pages",
    num_results: Annotated[
        int,
        "Maximum number of search results to return (default 10, max 25)",
    ] = 10,
) -> dict:
    """Search the web using FastSearch.

    Args:
        queries: One or more search queries. Pass every distinct
            query you need this turn as one list — do not call this
            tool multiple times in the same turn.
        search_type: Content type filter.
        num_results: Max results to return.

    Returns:
        Dict with ``"results"`` (list of per-query entries) and
        ``"summary"`` (formatted str aggregating all queries).
    """
    from airunner_services.llm.safety.account_context import (
        get_current_account_id,
    )
    from airunner_services.llm.safety.search_rate_limiter import (
        check_search_rate_limit,
    )

    account_id = get_current_account_id()
    provider = _get_provider()
    _validate_search_type(search_type)
    num_results = min(num_results, 25)

    queries = _truncate_queries(queries, "search_fastsearch")

    # Consume one rate-limit slot per query being dispatched.
    # Queries that fail the check get error entries; the rest
    # proceed concurrently as before.
    accepted: list[str] = []
    accepted_positions: list[int] = []
    rate_limited_positions: set[int] = set()
    for idx, q in enumerate(queries):
        if check_search_rate_limit(account_id):
            accepted.append(q)
            accepted_positions.append(idx)
        else:
            rate_limited_positions.add(idx)

    # Run accepted queries concurrently.  Results are in the same
    # order as *accepted*, so we can map them back to original
    # positions without relying on query-string uniqueness.
    position_results: dict[int, dict] = {}
    position_parts: dict[int, str] = {}
    if accepted:
        async def _do_search(query: str, session) -> list[dict]:
            return await provider.search(
                query,
                search_type=search_type,
                num_results=num_results,
                client=session,
            )

        raw_results = _run_async(
            _execute_concurrent_queries(accepted, _do_search)
        )

        concurrent_results, concurrent_parts = (
            _process_search_results(
                raw_results, search_type, "search_fastsearch"
            )
        )
        for pos, entry, part in zip(
            accepted_positions, concurrent_results, concurrent_parts
        ):
            position_results[pos] = entry
            position_parts[pos] = part

    # Build output in original query order by position.
    per_query_results: list[dict] = []
    formatted_parts: list[str] = []
    for idx, q in enumerate(queries):
        if idx in rate_limited_positions:
            logger.warning(
                "FastSearch rate limit hit on query '%s'", q[:80]
            )
            per_query_results.append({"query": q, "results": []})
            formatted_parts.append(
                f"Search rate limit reached on '{q}'. "
                "Try again in a few seconds."
            )
        else:
            per_query_results.append(position_results[idx])
            formatted_parts.append(position_parts[idx])
    formatted_parts, per_query_results = cap_query_blocks(
        formatted_parts, per_query_results
    )
    # "summary" is listed first so the clean, length-capped prose
    # appears before the bulky "results" array when serialized.
    # If the ToolMessage gets truncated at 4000 chars, the summary
    # (already capped via cap_query_blocks) survives intact rather
    # than being lost behind raw result data.
    return {
        "summary": "\n\n".join(formatted_parts),
        "results": per_query_results,
    }


def _sanitize_news_query(query: str) -> str:
    """Strip trailing date patterns from a free-text news query.

    This is a defensive safety net — the LLM may embed literal dates
    (``2026-07-06``, ``today July 6 2026``) in the query despite tool
    description instructions.  Only tail-anchored patterns are removed
    so legitimate mid-query text is never touched.
    """
    return _TAIL_DATE_RE.sub("", query).strip()


@tool(
    name="search_fastsearch_news",
    category=ToolCategory.RESEARCH,
    description=(
        "Search for recent news articles using FastSearch's news index. "
        "Returns news articles with titles, URLs, snippets, sources, and "
        "publication dates. Use this for current events, breaking news, "
        "or time-sensitive information. "
        "Keep query topical — strip dates and years (freshness is "
        "automatic) but KEEP event-type nouns (\"speech\", \"eulogy\", "
        "\"announcement\", \"debate\") that identify a specific "
        "occurrence. e.g. \"policy speech reaction\" not bare \"US news\". "
        "Pass every distinct query you need this turn as one list in a "
        "single call — do not call this tool multiple times in the same turn."
    ),
    return_direct=False,
    requires_api=True,
    defer_loading=True,
    keywords=[
        "fastsearch",
        "news",
        "current events",
        "breaking news",
        "articles",
    ],
    input_examples=[
        {"queries": ["policy speech reaction"]},
        {
            "queries": [
                "trade deal announcement fallout",
                "tariff impact on manufacturing",
            ],
        },
    ],
)
def search_fastsearch_news(
    queries: Annotated[
        list[str],
        "One or more topical news search queries. "
        "Do NOT embed dates or years (freshness is automatic), "
        "but DO keep event-type nouns (\"speech\", \"announcement\", "
        "\"debate\") that identify a specific occurrence. "
        "Pass every distinct query you need this turn as one list "
        "in a single call — do not call this tool multiple times "
        "in the same turn.",
    ],
    num_results: Annotated[
        int,
        "Maximum number of news results to return (default 10, max 25)",
    ] = 10,
    max_age_hours: Annotated[
        int | None,
        "Maximum age of articles in hours (default 24). "
        "Lower = fresher but may miss older context.",
    ] = 24,
    country: Annotated[
        str | None,
        "Optional ISO 3166-1 alpha-2 country code for geographic "
        "scoping (e.g. \"us\", \"gb\").",
    ] = None,
) -> dict:
    """Search for recent news articles using FastSearch.

    Args:
        queries: One or more news search queries. Pass every distinct
            query you need this turn as one list — do not call this
            tool multiple times in the same turn.
        num_results: Max results to return.
        max_age_hours: Maximum article age in hours.
        country: Optional ISO 3166-1 alpha-2 country code.

    Returns:
        Dict with ``"results"`` (list of per-query entries) and
        ``"summary"`` (formatted str aggregating all queries).
    """
    from airunner_services.llm.safety.account_context import (
        get_current_account_id,
    )
    from airunner_services.llm.safety.search_rate_limiter import (
        check_search_rate_limit,
    )

    account_id = get_current_account_id()
    provider = _get_provider()
    num_results = min(num_results, 25)

    queries = _truncate_queries(queries, "search_fastsearch_news")

    # Consume one rate-limit slot per query being dispatched.
    accepted_originals: list[str] = []
    accepted_sanitized: list[str] = []
    rate_limited: set[str] = set()
    for q in queries:
        sanitized = _sanitize_news_query(q)
        if check_search_rate_limit(account_id):
            accepted_originals.append(q)
            accepted_sanitized.append(sanitized)
        else:
            rate_limited.add(q)

    # Run accepted queries concurrently.
    accepted_results: dict[str, dict] = {}
    accepted_parts: dict[str, str] = {}
    if accepted_sanitized:
        async def _do_news_search(
            query: str, session,
        ) -> list[dict]:
            return await provider.search_news(
                query,
                num_results=num_results,
                max_age_hours=max_age_hours,
                country=country,
                client=session,
            )

        raw_results = _run_async(
            _execute_concurrent_queries(
                accepted_sanitized, _do_news_search,
            )
        )

        concurrent_results, concurrent_parts = (
            _process_news_results(
                raw_results,
                accepted_originals,
                num_results,
            )
        )
        for entry, part in zip(
            concurrent_results, concurrent_parts
        ):
            accepted_results[entry["query"]] = entry
            accepted_parts[entry["query"]] = part

    # Build output in original query order.
    per_query_results: list[dict] = []
    formatted_parts: list[str] = []
    for q in queries:
        if q in rate_limited:
            logger.warning(
                "FastSearch news rate limit hit on query '%s'",
                q[:80],
            )
            per_query_results.append({"query": q, "results": []})
            formatted_parts.append(
                f"News search rate limit reached on '{q}'. "
                "Try again in a few seconds."
            )
        else:
            per_query_results.append(accepted_results[q])
            formatted_parts.append(accepted_parts[q])

    formatted_parts, per_query_results = cap_query_blocks(
        formatted_parts, per_query_results
    )
    return {
        "results": per_query_results,
        "summary": "\n\n".join(formatted_parts),
    }


@tool(
    name="get_topic_brief",
    category=ToolCategory.RESEARCH,
    description=(
        "Get a compiled, sourced topic brief on any subject. "
        "Returns a structured markdown document assembled from "
        "real web content — far richer than a list of search "
        "snippets. Use this when the user asks about a specific "
        "topic, person, event, show, news story, or cultural "
        "reference. Prefer this over search_fastsearch_news."
    ),
    return_direct=False,
    requires_api=True,
    defer_loading=True,
    keywords=[
        "topic",
        "brief",
        "summary",
        "research",
        "explain",
        "what is",
        "who is",
        "news",
        "event",
        "show",
        "episode",
    ],
    input_examples=[
        {"query": "latest developments in fusion energy research"},
        {
            "query": "most recent season of a popular streaming series",
        },
    ],
)
def get_topic_brief(
    query: Annotated[str, "The topic or question to research"],
    max_sources: Annotated[
        int,
        "Max pages to compile into the brief (default 5, max 8)",
    ] = 5,
) -> dict:
    """Fetch a topic brief from FastSearch.

    Returns a dict with brief (markdown str or None), sources
    (list), confidence ('high'/'medium'/'low'), and cached (bool).
    If the endpoint is unavailable, returns confidence='low' and
    brief=None so the caller can degrade gracefully.
    """
    from airunner_services.llm.safety.account_context import (
        get_current_account_id,
    )
    from airunner_services.llm.safety.search_rate_limiter import (
        check_search_rate_limit,
    )

    account_id = get_current_account_id()
    if not check_search_rate_limit(account_id):
        return {
            "brief": None,
            "sources": [],
            "confidence": "low",
            "summary": "Topic brief rate limit reached. "
            "Please wait a moment before requesting another brief.",
        }

    provider = _get_provider()
    max_sources = min(max_sources, 8)
    try:
        result = _run_async(
            provider.get_topic_brief(query, max_sources=max_sources)
        )
    except Exception as exc:
        logger.error(
            "get_topic_brief error (%s): %s", query[:80], exc
        )
        return {
            "brief": None,
            "sources": [],
            "confidence": "low",
            "summary": f"Topic brief lookup failed: {exc}",
        }
    brief = result.get("brief")
    if not brief:
        return {
            "brief": None,
            "sources": result.get("sources", []),
            "confidence": "low",
            "summary": f"No topic brief found for '{query}'.",
        }
    brief = _truncate_brief(brief, _TOPIC_BRIEF_MAX_CHARS)
    sources = result.get("sources", [])
    source_lines = "\n".join(
        f"- [{s.get('title', s.get('url', ''))}]({s.get('url', '')})"
        for s in sources
    )
    summary = brief
    if source_lines:
        summary += f"\n\n---\n**Sources:**\n{source_lines}"
    summary = _scan_tool_output(
        summary, f"get_topic_brief:{query[:50]}"
    )
    return {
        "brief": brief,
        "sources": sources,
        "confidence": result.get("confidence", "low"),
        "cached": result.get("cached", False),
        "summary": summary,
    }


@tool(
    name="read_url",
    category=ToolCategory.KNOWLEDGE,
    description=(
        "Fetch and read the contents of a web page or URL the user has "
        "shared. Use this whenever the user pastes a link and wants "
        "you to read it."
    ),
    return_direct=False,
    requires_api=True,
    defer_loading=True,
    keywords=[
        "read",
        "url",
        "link",
        "website",
        "article",
        "blog",
        "page",
        "open",
        "visit",
        "check",
    ],
    input_examples=[
        {"url": "https://example.com/article"},
    ],
)
def read_url(
    url: Annotated[str, "The full URL to fetch and read"],
) -> str:
    """Fetch and read the contents of a web page.

    Returns the page title and cleaned plain-text content (truncated
    at 4000 characters).

    Args:
        url: The full URL to fetch.

    Returns:
        Formatted string with title, URL, and content.
    """
    from airunner_services.llm.safety.account_context import (
        get_current_account_id,
    )
    from airunner_services.llm.safety.search_rate_limiter import (
        check_search_rate_limit,
    )

    account_id = get_current_account_id()
    if not check_search_rate_limit(account_id):
        return (
            "URL read rate limit reached. Please wait a moment "
            "before fetching another URL."
        )

    from airunner_services.url_safety import (
        SSRFBlocked,
        validate_url_for_fetch,
    )

    # SSRF guard — reject internal / private targets.
    try:
        validate_url_for_fetch(url)
    except SSRFBlocked as exc:
        from airunner_services.llm.safety.account_context import (
            get_current_account_id,
        )
        from airunner_services.llm.safety.security_counters import (
            increment_ssrf_block,
        )

        account_id = get_current_account_id()
        if account_id is not None:
            increment_ssrf_block(account_id)
        return f"Could not read that URL: {exc}"

    provider = _get_provider()

    try:
        data = _run_async(provider.scrape_url(url))
    except Exception as exc:
        return (
            f"Could not read that URL: {exc}"
        )

    if not data or "error" in data:
        reason = (data.get("error") if data else "No response")
        return f"Could not read that URL: {reason}"

    title = data.get("title", "Untitled")
    content = data.get("content", "")
    # Truncate to 4000 characters (existing limit).
    content = content[:4000]

    # Scan for prompt-injection patterns in fetched content.
    from airunner_services.llm.safety.content_injection_scan import (
        scan_and_log_injection,
    )
    from airunner_services.llm.safety.account_context import (
        get_current_account_id,
    )
    from urllib.parse import urlparse

    host = urlparse(url).hostname or "unknown"
    account_id = get_current_account_id()
    content, _ = scan_and_log_injection(
        content,
        source_label=f"read_url:{host}",
        account_id=account_id,
    )

    return f"Title: {title}\nURL: {url}\n\n{content}"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&quot;", '"').replace("&amp;", "&")
    text = text.replace("&#39;", "'").replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    return " ".join(text.split())


_SEARCH_TYPES = {"all", "pages", "images", "news", "books"}


def _validate_search_type(search_type: str) -> None:
    """Raise ``ValueError`` if *search_type* is not recognised."""
    if search_type not in _SEARCH_TYPES:
        raise ValueError(
            f"Unknown search_type '{search_type}'. "
            f"Must be one of: {', '.join(sorted(_SEARCH_TYPES))}"
        )


def _format_results(
    query: str,
    results: list[dict],
    search_type: str,
) -> str:
    """Format a list of search results into a human-readable string."""
    formatted = (
        f"FastSearch results for '{query}' "
        f"(type: {search_type}):\n\n"
    )

    for i, r in enumerate(results[:10], 1):
        title = r.get("title", "N/A")
        link = r.get("link", "#")
        snippet = _strip_html((r.get("snippet", "") or ""))[:200]
        source = r.get("source", "")
        date = r.get("date", "")

        formatted += f"{i}. {title}\n"
        formatted += f"   URL: {link}\n"
        if source:
            formatted += f"   Source: {source}"
        if date:
            formatted += f" | Date: {date}"
        if source or date:
            formatted += "\n"
        if snippet:
            formatted += f"   {snippet}...\n"
        formatted += "\n"

    return formatted


def _scan_tool_output(text: str, source_label: str = "") -> str:
    """Scan tool output for prompt-injection patterns.

    Returns cleaned text with suspicious spans replaced by a
    neutral placeholder.  Increments the per-account security
    counter when account context is set.
    """
    from airunner_services.llm.safety.content_injection_scan import (
        scan_and_log_injection,
    )
    from airunner_services.llm.safety.account_context import (
        get_current_account_id,
    )

    account_id = get_current_account_id()
    cleaned, _ = scan_and_log_injection(
        text, source_label, account_id=account_id,
    )
    return cleaned
