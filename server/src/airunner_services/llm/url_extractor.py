"""Auto-extract URLs from user messages and store them as knowledge facts.

URLs are a special case of user-provided information: they are
unambiguous, high-value, and lost by every other memory mechanism
(session summaries drop them; the LLM does not reliably self-report
them).  Storing them here ensures they survive session resets.

Each URL is scraped via the FastSearch API (not directly by AIRunner)
and the content is injected into the LLM's conversation as a system
message so it can respond immediately.
"""

from __future__ import annotations

import logging
import os
import re

import requests as _requests

from airunner_services.utils.application.log_hygiene import (
    fingerprint_value,
)

logger = logging.getLogger(__name__)

_URL_RE = re.compile(
    r"https?://[^\s\"'<>(){}\[\]]+",
    re.IGNORECASE,
)
_MAX_CONTEXT_CHARS = 120
_MAX_CONTENT_CHARS = 2000
_SCRAPE_TIMEOUT = 5.0


def extract_and_store_urls(
    user_input: str,
    chatbot_id: int | None,
) -> list[str]:
    """Store URLs from *user_input* and return scraped content blocks.

    Each URL is stored as a KnowledgeFact.  Additionally, every URL
    is scraped via FastSearch's /api/scrape/ endpoint and the content
    is returned so the caller can inject it into the LLM's prompt.

    Returns a list of content strings, one per successfully scraped URL.
    """
    if not user_input or not user_input.strip():
        return []
    urls = _URL_RE.findall(user_input)
    if not urls:
        return []

    scraped: list[str] = []

    try:
        from airunner_services.knowledge import get_knowledge_base
        from airunner_services.knowledge_context import (
            set_knowledge_chatbot_id,
            set_knowledge_subject,
        )

        set_knowledge_chatbot_id(chatbot_id)
        set_knowledge_subject("user")
        kb = get_knowledge_base()
        context = user_input.strip()[:_MAX_CONTEXT_CHARS]

        for url in urls:
            fact = (
                f"User shared link: {url}"
                f" — context: \"{context}\""
            )
            stored = kb.add_fact(fact, source_type="inferred")
            if stored:
                logger.info(
                    "[URL EXTRACT] Stored URL fact (%d chars)",
                    len(fact),
                )

        # Scrape each unique URL via FastSearch
        unique_urls = list(dict.fromkeys(urls))
        for url in unique_urls:
            content = _scrape_via_fastsearch(url)
            if content:
                scraped.append(content)

    except Exception as exc:
        logger.debug("[URL EXTRACT] Failed: %s", exc)
    finally:
        try:
            set_knowledge_subject("user")
        except Exception:
            pass

    return scraped


def _scrape_via_fastsearch(url: str) -> str | None:
    """Scrape *url* via the FastSearch /api/scrape/ endpoint.

    Returns a formatted content string suitable for prompt injection,
    or None on failure.
    """
    from airunner_services.url_safety import SSRFBlocked
    from airunner_services.url_safety import validate_url_for_fetch

    try:
        validate_url_for_fetch(url)
    except SSRFBlocked:
        logger.debug(
            "[URL EXTRACT] SSRF guard blocked URL: %s",
            fingerprint_value(url),
        )
        return None

    base_url = os.environ.get("FASTSEARCH_BASE_URL", "").rstrip("/")
    api_key = os.environ.get("FASTSEARCH_API_KEY", "")
    if not base_url:
        logger.debug("[URL EXTRACT] FASTSEARCH_BASE_URL not set")
        return None

    try:
        headers = {"X-API-Key": api_key} if api_key else {}
        resp = _requests.get(
            f"{base_url}/api/scrape/",
            params={"url": url},
            headers=headers,
            timeout=_SCRAPE_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug(
            "[URL EXTRACT] FastSearch scrape failed for %s: %s",
            fingerprint_value(url),
            exc,
        )
        return None

    if data.get("error"):
        logger.debug(
            "[URL EXTRACT] FastSearch error for %s: %s",
            fingerprint_value(url),
            data["error"],
        )
        return None

    title = data.get("title") or ""
    content = (data.get("content") or "").strip()
    if not content:
        logger.debug(
            "[URL EXTRACT] Empty content for %s",
            fingerprint_value(url),
        )
        return None

    content = content[:_MAX_CONTENT_CHARS]
    if title:
        return (
            f"The user shared this link: {url}\n"
            f"Title: {title}\n"
            f"Content: {content}"
        )
    return (
        f"The user shared this link: {url}\n"
        f"Content: {content}"
    )
