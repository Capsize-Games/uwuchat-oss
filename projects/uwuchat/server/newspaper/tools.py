"""LLM tools for the newspaper system.

Registered with ``ToolRegistry`` via the ``@tool`` decorator.
The import is triggered by loading the newspaper module.
"""

from __future__ import annotations

from typing import Annotated

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application.get_logger import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


@tool(
    name="get_daily_newspaper",
    category=ToolCategory.KNOWLEDGE,
    description=(
        "Get today's curated news digest as a formatted newspaper. "
        "Includes headlines, short summaries, weather, and categorized "
        "sections (top news, US, world, tech, entertainment, sports, etc.). "
        "Use this to stay informed about current events, find talking "
        "points, or answer questions about what's happening today."
    ),
    return_direct=False,
    requires_api=True,
    defer_loading=True,
    keywords=[
        "newspaper",
        "news",
        "daily",
        "today",
        "headlines",
        "weather",
        "current events",
        "digest",
    ],
    input_examples=[
        {},
        {"location": "Denver, CO"},
        {"interests": "technology,science"},
    ],
)
def get_daily_newspaper(
    location: Annotated[
        str | None,
        "Optional location for weather and local news "
        "(e.g. 'Denver, CO', 'New York, NY')",
    ] = None,
    interests: Annotated[
        str | None,
        "Optional comma-separated interest tags for personalized "
        "sections (e.g. 'technology,science,movies')",
    ] = None,
) -> dict:
    """Return the daily newspaper as formatted markdown.

    Fetches from FastSearch via :class:`NewspaperProxy`, which caches
    the result for 15 minutes.

    Args:
        location: Optional location string for weather.
        interests: Optional comma-separated interest tags.

    Returns:
        Dict with ``"newspaper"`` (markdown str) and ``"cached"`` (bool).
    """
    import asyncio

    try:
        from extensions.fastsearch.server.provider import (
            FastSearchProvider,
        )
        from projects.uwuchat.server.newspaper.proxy import (
            NewspaperProxy,
        )

        provider = FastSearchProvider()
        proxy = NewspaperProxy(provider)
        markdown = asyncio.run(
            proxy.get_newspaper(
                location=location,
                interests=interests,
            )
        )
        return {
            "newspaper": markdown,
            "cached": True,
            "instructions": (
                "📰 The newspaper above contains today's headlines, "
                "weather, and categorized sections. You can reference "
                "specific stories, summarize sections for the user, or "
                "use `search_news` / `search_fastsearch_news` to dive "
                "deeper into any topic mentioned."
            ),
        }
    except Exception as exc:
        logger.error(
            "get_daily_newspaper failed: %s",
            exc,
            exc_info=True,
        )
        return {
            "newspaper": "",
            "cached": False,
            "error": str(exc),
            "summary": (
                "Could not fetch the daily newspaper. "
                "Try using search_news or search_fastsearch_news "
                "for specific queries instead."
            ),
        }


@tool(
    name="summarize_article",
    category=ToolCategory.KNOWLEDGE,
    description=(
        "Generate a high-quality 1-2 sentence summary of an article. "
        "Use this when the user asks for a quick summary of a specific "
        "news story or URL. Produces better summaries than those in "
        "the daily newspaper."
    ),
    return_direct=False,
    requires_api=True,
    defer_loading=True,
    keywords=[
        "summarize",
        "summary",
        "article",
        "tl;dr",
        "tldr",
        "recap",
    ],
    input_examples=[
        {"url": "https://example.com/article"},
        {"text": "Long article text here..."},
    ],
)
def summarize_article(
    url: Annotated[
        str | None,
        "URL of the article to summarize",
    ] = None,
    text: Annotated[
        str | None,
        "Text content to summarize (use this if you already have "
        "the article content)",
    ] = None,
) -> dict:
    """Generate an LLM-quality summary of an article.

    Provide either *url* or *text*.  If both are given, *url* takes
    precedence.

    Args:
        url: Article URL to fetch and summarise.
        text: Raw article text to summarise.

    Returns:
        Dict with ``"summary"`` (str) and optional ``"url"`` / ``"error"``.
    """
    import asyncio

    try:
        from projects.uwuchat.server.newspaper.summarizer import (
            ArticleSummarizer,
        )

        summarizer = ArticleSummarizer()
        if url:
            summary = asyncio.run(summarizer.summarize_url(url))
            return {"summary": summary, "url": url}
        if text:
            summary = asyncio.run(summarizer.summarize_text(text))
            return {"summary": summary}
        return {
            "summary": "",
            "error": "Provide a URL or text to summarise.",
        }
    except Exception as exc:
        logger.error(
            "summarize_article failed: %s",
            exc,
            exc_info=True,
        )
        return {"summary": "", "error": str(exc)}
