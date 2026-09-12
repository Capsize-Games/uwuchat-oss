"""Shared fixtures for FastSearch extension tests.

Provides mock HTTP response data and a pre-configured
``FastSearchProvider`` backed by ``unittest.mock`` so tests
do not require a live FastSearch instance.
"""

from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest


# ------------------------------------------------------------------
# Sample API response data
# ------------------------------------------------------------------


@pytest.fixture
def sample_search_response() -> Dict[str, Any]:
    """Simulate a unified search response from ``/api/search/``."""
    return {
        "results": [
            {
                "type": "page",
                "id": 1,
                "title": "Python Tutorial",
                "url": "https://docs.python.org/3/tutorial/",
                "snippet": "Python is an easy to learn, powerful language.",
            },
            {
                "type": "image",
                "id": 42,
                "alt": "Python logo",
                "ai_caption": "The Python programming language logo",
                "url": "https://python.org/logo.png",
            },
            {
                "type": "news",
                "id": 5,
                "title": "Python 3.14 Released",
                "url": "https://example.com/python-314",
                "source": "Example News",
                "published_at": "2026-06-08T12:00:00Z",
                "snippet": "The latest version of Python is now available.",
            },
            {
                "type": "web",
                "source": "wikipedia",
                "title": "Python (programming language)",
                "url": "https://en.wikipedia.org/wiki/Python",
                "snippet": "Python is a high-level general-purpose language.",
            },
        ],
        "query": "python",
        "page": 1,
        "search_type": "all",
    }


@pytest.fixture
def sample_news_response() -> Dict[str, Any]:
    """Simulate a news API response from ``/news/api/news/``."""
    return {
        "articles": [
            {
                "id": 1,
                "title": "Breaking News: Major Discovery",
                "url": "https://example.com/article-1",
                "source_name": "BBC News",
                "description": "Scientists have made a major breakthrough.",
                "published_at": "2026-06-08T12:00:00Z",
                "image_url": "https://example.com/thumb.jpg",
            },
            {
                "id": 2,
                "title": "Technology Stocks Surge",
                "url": "https://example.com/article-2",
                "source_name": "Reuters",
                "description": "Markets react positively to new policies.",
                "published_at": "2026-06-07T08:30:00Z",
                "image_url": "https://example.com/thumb2.jpg",
            },
        ],
        "page": 1,
        "per_page": 20,
        "total": 150,
    }


@pytest.fixture
def sample_images_response() -> Dict[str, Any]:
    """Simulate an images API response from ``/api/images/``."""
    return {
        "results": [
            {
                "id": 10,
                "alt": "Sunset over mountains",
                "ai_caption": "A beautiful sunset landscape photo",
                "url": "https://example.com/sunset.jpg",
            },
        ],
    }


@pytest.fixture
def sample_empty_response() -> Dict[str, Any]:
    """Simulate an API response with no results."""
    return {"results": []}


@pytest.fixture
def sample_health_response() -> Dict[str, Any]:
    """Simulate a health check response."""
    return {"status": "ok", "database": "connected"}


# ------------------------------------------------------------------
# Mocked provider fixture
# ------------------------------------------------------------------


@pytest.fixture
def mock_provider() -> Any:
    """Return a ``FastSearchProvider`` whose ``_request`` is mocked.

    The mock returns empty results by default.  Override the return
    value in individual tests by accessing
    ``mock_provider._request.return_value``.
    """
    from extensions.fastsearch.server.provider import (
        FastSearchProvider,
    )

    provider = FastSearchProvider(
        base_url="http://mock-fastsearch:8001",
        api_key="test-api-key",
    )
    provider._request = AsyncMock(
        return_value={"results": []},
    )
    return provider
