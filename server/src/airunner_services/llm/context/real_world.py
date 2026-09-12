"""Standalone real-world context fetch functions for per-turn injection.

Weather has been consolidated into
``airunner_services.services.weather_service``.
This module now only provides news headline fetching.
No function exceeds 20 lines.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_NEWS_RESULTS = 4
_FASTSEARCH_DEFAULT_URL = "http://127.0.0.1:8001"
_NEWS_REQUEST_TIMEOUT = 30
_NEWS_MAX_AGE_HOURS = 24


def _build_news_url() -> str:
    """Return the FastSearch news endpoint URL."""
    base = os.environ.get(
        "FASTSEARCH_BASE_URL", _FASTSEARCH_DEFAULT_URL,
    ).rstrip("/")
    return f"{base}/api/news/latest-summary/"


def _parse_news_results(resp, n: int) -> list[str]:
    """Extract up to *n* headline strings from the API response."""
    results = resp.json().get("results", [])
    return [
        r["title"]
        for r in results[:n]
        if isinstance(r, dict) and r.get("title")
    ]


def _log_news_error(exc: Exception) -> None:
    """Classify and log a news-fetch exception."""
    from airunner_services.utils.network_retry import (
        is_http_service_error,
        is_transient_network_error,
        log_network_failure,
    )
    if is_transient_network_error(exc) or is_http_service_error(exc):
        log_network_failure(
            logger, "FastSearch news fetch failed", exc,
        )
    else:
        logger.error(
            "FastSearch news fetch failed", exc_info=True,
        )


def _do_news_request(
    n: int, max_age_hours: int,
) -> list[str] | None:
    """Make the HTTP request and return headlines or None on error."""
    import requests

    api_key = os.environ.get("FASTSEARCH_API_KEY", "")
    if not api_key:
        return []
    resp = requests.get(
        _build_news_url(),
        headers={"X-API-Key": api_key},
        params={"q": "news", "limit": n,
                "max_age_hours": max_age_hours},
        timeout=_NEWS_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return _parse_news_results(resp, n)


def _fetch_news_from_fastsearch(
    n: int, max_age_hours: int = _NEWS_MAX_AGE_HOURS
) -> list[str]:
    try:
        return _do_news_request(n, max_age_hours) or []
    except Exception as exc:
        _log_news_error(exc)
        return []


def fetch_news_headlines(n: int = _NEWS_RESULTS) -> list[str]:
    """Return up to n recent news headlines via FastSearch."""
    return _fetch_news_from_fastsearch(n)
