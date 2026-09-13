"""Tests for web_tools search/news functions and return shapes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests as _requests_mod  # for patching


class TestFastsearchResults:
    """Tests for _fastsearch_results content_summary preference."""

    def test_prefers_content_summary_over_raw_content(self) -> None:
        """When content_summary is present, use it as entry['content']."""
        from airunner_services.tools.web_tools import (
            _fastsearch_results,
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Article",
                    "source_url": "https://example.com/a",
                    "summary": "Short editorial description",
                    "source": "Example News",
                    "published_at": "2026-01-15T12:00:00Z",
                    "content": "x" * 2000,
                    "content_summary": "Summary of the article.",
                    "is_scraped": True,
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            _requests_mod, "get", return_value=mock_response
        ), patch.dict(
            "os.environ",
            {
                "FASTSEARCH_BASE_URL": "http://fs.example",
                "FASTSEARCH_API_KEY": "k",
            },
            clear=False,
        ):
            results = _fastsearch_results("test", search_type="news")

        assert len(results) == 1
        assert results[0]["content"] == "Summary of the article."
        assert results[0]["is_scraped"] is True

    def test_falls_back_to_truncated_content_when_no_summary(
        self,
    ) -> None:
        """When content_summary is absent, fall back to truncated content."""
        from airunner_services.tools.web_tools import (
            _fastsearch_results,
        )

        raw = "A" * 2000
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Article",
                    "source_url": "https://example.com/a",
                    "summary": "Short editorial description",
                    "source": "Example News",
                    "published_at": "2026-01-15T12:00:00Z",
                    "content": raw,
                    "is_scraped": True,
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            _requests_mod, "get", return_value=mock_response
        ), patch.dict(
            "os.environ",
            {
                "FASTSEARCH_BASE_URL": "http://fs.example",
                "FASTSEARCH_API_KEY": "k",
            },
            clear=False,
        ):
            results = _fastsearch_results("test", search_type="news")

        assert len(results) == 1
        assert results[0]["content"] == raw[:500]
        assert results[0]["is_scraped"] is True

    def test_empty_content_summary_falls_back_to_truncated(
        self,
    ) -> None:
        """When content_summary is empty string, fall back to truncated."""
        from airunner_services.tools.web_tools import (
            _fastsearch_results,
        )

        raw = "B" * 800
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Article",
                    "source_url": "https://example.com/a",
                    "summary": "Short editorial description",
                    "source": "Example News",
                    "published_at": "2026-01-15T12:00:00Z",
                    "content": raw,
                    "content_summary": "",
                    "is_scraped": True,
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            _requests_mod, "get", return_value=mock_response
        ), patch.dict(
            "os.environ",
            {
                "FASTSEARCH_BASE_URL": "http://fs.example",
                "FASTSEARCH_API_KEY": "k",
            },
            clear=False,
        ):
            results = _fastsearch_results("test", search_type="news")

        assert len(results) == 1
        assert results[0]["content"] == raw[:500]


class TestSearchNewsReturnShape:
    """Tests that search_news returns a plain string, not a dict."""

    def test_search_news_returns_string_on_success(self) -> None:
        """search_news must return a formatted string, not a dict."""
        from airunner_services.tools.web_tools import search_news

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Article",
                    "source_url": "https://example.com/a",
                    "summary": "Short editorial description",
                    "source": "Example News",
                    "published_at": "2026-01-15T12:00:00Z",
                    "content": "x" * 2000,
                    "content_summary": "Summary.",
                    "is_scraped": True,
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            _requests_mod, "get", return_value=mock_response
        ), patch.dict(
            "os.environ",
            {
                "FASTSEARCH_BASE_URL": "http://fs.example",
                "FASTSEARCH_API_KEY": "k",
            },
            clear=False,
        ), patch(
            "airunner_services.tools.web_tools._check_search_rate_limit",
            return_value=True,
        ), patch(
            "airunner_services.tools.web_tools._respect_search_cooldown",
        ):
            result = search_news("test query")

        assert isinstance(result, str), (
            f"Expected str, got {type(result).__name__}"
        )
        assert "test query" in result
        assert "Test Article" in result


class TestSearchWebReturnShape:
    """Tests that search_web returns a plain string, not a dict."""

    def test_search_web_returns_string_on_success(self) -> None:
        """search_web must return a formatted string, not a dict."""
        from airunner_services.tools.web_tools import search_web

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Test Result",
                    "url": "https://example.com/r",
                    "snippet": "A test result snippet.",
                    "source": "Example",
                    "published_at": "2026-01-15T12:00:00Z",
                },
            ],
        }
        mock_response.raise_for_status = MagicMock()

        with patch.object(
            _requests_mod, "get", return_value=mock_response
        ), patch.dict(
            "os.environ",
            {
                "FASTSEARCH_BASE_URL": "http://fs.example",
                "FASTSEARCH_API_KEY": "k",
            },
            clear=False,
        ), patch(
            "airunner_services.tools.web_tools._check_search_rate_limit",
            return_value=True,
        ), patch(
            "airunner_services.tools.web_tools._respect_search_cooldown",
        ):
            result = search_web("test query")

        assert isinstance(result, str), (
            f"Expected str, got {type(result).__name__}"
        )
        assert "test query" in result
        assert "Test Result" in result
