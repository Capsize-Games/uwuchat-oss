"""Unit tests for ``FastSearchProvider``.

All tests use a mocked ``_request`` method so they don't require
a live FastSearch instance.
"""

from __future__ import annotations

import pytest


class TestFastSearchProvider:
    """Test suite for the FastSearchProvider class."""

    # ------------------------------------------------------------------
    # search() — unified search
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_search_returns_formatted_results(
        self,
        mock_provider,
        sample_search_response,
    ):
        """Unified search should return formatted result dicts."""
        mock_provider._request.return_value = sample_search_response

        results = await mock_provider.search("python")

        assert len(results) == 4
        # First result is a page
        assert results[0]["title"] == "Python Tutorial"
        assert results[0]["link"] == "https://docs.python.org/3/tutorial/"
        assert "Python is an easy" in results[0]["snippet"]
        # Second result is an image
        assert results[1]["title"] == "Python logo"
        assert results[1]["link"] == "https://python.org/logo.png"
        # Third result is news
        assert results[2]["title"] == "Python 3.14 Released"
        assert results[2]["source"] == "Example News"
        assert results[2]["date"] == "2026-06-08T12:00:00Z"
        # Fourth result is web
        assert results[3]["title"] == "Python (programming language)"

    @pytest.mark.asyncio
    async def test_search_empty_results(self, mock_provider, sample_empty_response):
        """Empty API results should return an empty list."""
        mock_provider._request.return_value = sample_empty_response

        results = await mock_provider.search("nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_respects_num_results(self, mock_provider, sample_search_response):
        """The num_results parameter should cap the returned list."""
        mock_provider._request.return_value = sample_search_response

        results = await mock_provider.search("python", num_results=2)
        assert len(results) == 2

    # ------------------------------------------------------------------
    # search_news()
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_search_news_formats_correctly(self, mock_provider):
        """News search (unified endpoint) should return results with source and date."""
        mock_provider._request.return_value = {
            "results": [
                {
                    "type": "news",
                    "id": 1,
                    "title": "Breaking News: Major Discovery",
                    "url": "https://example.com/article-1",
                    "snippet": "Scientists have made a major breakthrough.",
                    "source": "BBC News",
                    "published_at": "2026-06-08T12:00:00Z",
                },
                {
                    "type": "news",
                    "id": 2,
                    "title": "Technology Stocks Surge",
                    "url": "https://example.com/article-2",
                    "snippet": "Markets react positively to new policies.",
                    "source": "Reuters",
                    "published_at": "2026-06-07T08:30:00Z",
                },
            ],
        }

        results = await mock_provider.search_news("breaking news")

        assert len(results) == 2
        assert results[0]["title"] == "Breaking News: Major Discovery"
        assert results[0]["link"] == "https://example.com/article-1"
        assert results[0]["source"] == "BBC News"
        assert results[0]["date"] == "2026-06-08T12:00:00Z"
        assert "major breakthrough" in results[0]["snippet"]
        assert results[1]["source"] == "Reuters"

    @pytest.mark.asyncio
    async def test_search_news_empty(self, mock_provider):
        """Empty news results should return an empty list."""
        mock_provider._request.return_value = {"results": []}

        results = await mock_provider.search_news("nothing")
        assert results == []

    # ------------------------------------------------------------------
    # search_images()
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_search_images_formats_correctly(
        self,
        mock_provider,
        sample_images_response,
    ):
        """Image search should return results with alt/caption as title."""
        mock_provider._request.return_value = sample_images_response

        results = await mock_provider.search_images("sunset")

        assert len(results) == 1
        # Title should come from alt text
        assert results[0]["title"] == "Sunset over mountains"
        assert results[0]["link"] == "https://example.com/sunset.jpg"

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_search_network_error(self, mock_provider):
        """Network errors should propagate from _request."""
        mock_provider._request.side_effect = ConnectionError(
            "Connection refused"
        )

        with pytest.raises(ConnectionError):
            await mock_provider.search("python")

    @pytest.mark.asyncio
    async def test_search_timeout(self, mock_provider):
        """Timeout errors should propagate from _request."""
        import asyncio

        mock_provider._request.side_effect = asyncio.TimeoutError(
            "Request timed out"
        )

        with pytest.raises(asyncio.TimeoutError):
            await mock_provider.search("python")

    # ------------------------------------------------------------------
    # _request() internals
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_request_includes_api_key_header(self, mock_provider):
        """The API key should be sent as X-API-Key header."""
        # Re-mock _request so we can inspect call arguments
        mock_provider._request.return_value = {"results": []}

        await mock_provider.search("test")

        mock_provider._request.assert_called_once()
        call_kwargs = mock_provider._request.call_args

        # Verify it was called with expected params
        assert call_kwargs[0][0] == "GET"  # method
        assert "/api/search/" in call_kwargs[0][1]  # path
        assert call_kwargs[1]["params"]["q"] == "test"

    # ------------------------------------------------------------------
    # health()
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_health_ok(self, mock_provider):
        """health() should return ok=True when API is reachable."""
        mock_provider._request.return_value = {"status": "ok"}

        result = await mock_provider.health()
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_health_error(self, mock_provider):
        """health() should return ok=False with error on failure."""
        mock_provider._request.side_effect = ConnectionError("API down")

        result = await mock_provider.health()
        assert result["ok"] is False
        assert "API down" in result["error"]
