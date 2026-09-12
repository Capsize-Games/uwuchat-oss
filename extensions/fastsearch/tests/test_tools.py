"""Integration tests for FastSearch LLM tool functions.

Tests verify that:
- Tool functions are registered with the ``ToolRegistry``
- They return the expected ``{"results": [...], "summary": "..."}`` format
- Edge cases (empty results, errors) are handled gracefully
- Multi-query batching works correctly
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from extensions.fastsearch.server.tools import (
    get_topic_brief,
    search_fastsearch,
    search_fastsearch_news,
    _truncate_brief,
    _validate_search_type,
)


class TestSearchFastSearchTool:
    """Tests for the ``search_fastsearch`` tool function."""

    def test_search_returns_expected_structure(self):
        """Single query returns one entry in results list."""
        mock_results = [
            {
                "title": "Python Tutorial",
                "link": "https://docs.python.org/3/tutorial/",
                "snippet": "Python is an easy to learn language.",
            },
            {
                "title": "Python Docs",
                "link": "https://docs.python.org/3/",
                "snippet": "Official Python documentation.",
            },
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.search = AsyncMock(return_value=mock_results)

            result = search_fastsearch(
                queries=["python tutorial"],
                search_type="all",
                num_results=10,
            )

        assert "results" in result
        assert "summary" in result
        assert isinstance(result["results"], list)
        assert isinstance(result["summary"], str)
        # Outer list has one entry (one query)
        assert len(result["results"]) == 1
        # Inner per-query entry has 2 raw results
        assert len(result["results"][0]["results"]) == 2
        assert result["results"][0]["query"] == "python tutorial"
        assert "Python Tutorial" in result["summary"]
        assert "python tutorial" in result["summary"]

    def test_search_multi_query(self):
        """Multiple queries return one entry per query."""
        mock_results_q1 = [
            {
                "title": "Python Tutorial",
                "link": "https://docs.python.org/3/tutorial/",
                "snippet": "Python is an easy to learn language.",
            },
        ]
        mock_results_q2 = [
            {
                "title": "Java Tutorial",
                "link": "https://docs.oracle.com/javase/tutorial/",
                "snippet": "Java is a general-purpose language.",
            },
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.search = AsyncMock(side_effect=[
                mock_results_q1,
                mock_results_q2,
            ])

            result = search_fastsearch(
                queries=["python tutorial", "java tutorial"],
                search_type="all",
                num_results=10,
            )

        assert len(result["results"]) == 2
        assert result["results"][0]["query"] == "python tutorial"
        assert len(result["results"][0]["results"]) == 1
        assert result["results"][1]["query"] == "java tutorial"
        assert len(result["results"][1]["results"]) == 1
        assert "Python Tutorial" in result["summary"]
        assert "Java Tutorial" in result["summary"]

    def test_search_empty_results(self):
        """Empty results from the provider should return an appropriate message."""
        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.search = AsyncMock(return_value=[])

            result = search_fastsearch(queries=["nonexistent"])

        assert len(result["results"]) == 1
        assert result["results"][0]["results"] == []
        assert result["results"][0]["query"] == "nonexistent"
        assert "No results found" in result["summary"]

    def test_search_error_handling(self):
        """Provider errors should return a formatted error message."""
        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.search = AsyncMock(
                side_effect=ConnectionError("API unavailable")
            )

            result = search_fastsearch(queries=["test"])

        assert len(result["results"]) == 1
        assert result["results"][0]["results"] == []
        assert "FastSearch search failed" in result["summary"]

    def test_search_partial_failure(self):
        """One failing query should not prevent others from returning."""
        mock_results_q1 = [
            {
                "title": "Python Tutorial",
                "link": "https://docs.python.org/3/tutorial/",
                "snippet": "Python is an easy to learn language.",
            },
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.search = AsyncMock(side_effect=[
                mock_results_q1,
                ConnectionError("API unavailable"),
            ])

            result = search_fastsearch(
                queries=["python tutorial", "broken query"],
                search_type="all",
                num_results=10,
            )

        assert len(result["results"]) == 2
        # First query succeeded
        assert result["results"][0]["query"] == "python tutorial"
        assert len(result["results"][0]["results"]) == 1
        # Second query failed
        assert result["results"][1]["query"] == "broken query"
        assert result["results"][1]["results"] == []
        assert "Python Tutorial" in result["summary"]
        assert "FastSearch search failed" in result["summary"]

    def test_search_invalid_search_type(self):
        """An invalid search_type should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown search_type"):
            search_fastsearch(
                queries=["test"],
                search_type="invalid_type",
            )

    def test_search_caps_num_results(self):
        """num_results should be capped at 25."""
        mock_results = [
            {"title": f"Result {i}", "link": f"https://example.com/{i}", "snippet": ""}
            for i in range(30)
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.search = AsyncMock(return_value=mock_results)

            result = search_fastsearch(queries=["test"], num_results=50)

        provider.search.assert_called_once()
        _, kwargs = provider.search.call_args
        assert kwargs["num_results"] == 25
        assert "test" in result["summary"]


class TestSearchFastSearchNewsTool:
    """Tests for the ``search_fastsearch_news`` tool function."""

    def test_news_returns_expected_structure(self):
        """Single query returns one entry in results list."""
        mock_results = [
            {
                "title": "Breaking News",
                "link": "https://example.com/news/1",
                "snippet": "A major event occurred today.",
                "source": "BBC News",
                "date": "2026-06-08T12:00:00Z",
            },
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.search_news = AsyncMock(return_value=mock_results)

            result = search_fastsearch_news(queries=["breaking news"])

        assert "results" in result
        assert "summary" in result
        assert len(result["results"]) == 1
        assert result["results"][0]["query"] == "breaking news"
        assert len(result["results"][0]["results"]) == 1
        assert "Breaking News" in result["summary"]
        assert "BBC News" in result["summary"]
        assert "2026-06-08" in result["summary"]

    def test_news_multi_query(self):
        """Multiple news queries return one entry per query."""
        mock_results_q1 = [
            {
                "title": "Breaking News",
                "link": "https://example.com/news/1",
                "snippet": "A major event occurred today.",
                "source": "BBC News",
                "date": "2026-06-08T12:00:00Z",
            },
        ]
        mock_results_q2 = [
            {
                "title": "Tech Stocks Surge",
                "link": "https://example.com/news/2",
                "snippet": "Markets react positively.",
                "source": "Reuters",
                "date": "2026-06-07T08:30:00Z",
            },
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.search_news = AsyncMock(side_effect=[
                mock_results_q1,
                mock_results_q2,
            ])

            result = search_fastsearch_news(
                queries=["breaking news", "tech stocks"],
                num_results=10,
                max_age_hours=48,
                country="us",
            )

        assert len(result["results"]) == 2
        assert result["results"][0]["query"] == "breaking news"
        assert len(result["results"][0]["results"]) == 1
        assert result["results"][1]["query"] == "tech stocks"
        assert len(result["results"][1]["results"]) == 1
        assert "Breaking News" in result["summary"]
        assert "Tech Stocks Surge" in result["summary"]

    def test_news_empty_results(self):
        """Empty news results should return a clear message."""
        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.search_news = AsyncMock(return_value=[])

            result = search_fastsearch_news(queries=["nothing"])

        assert len(result["results"]) == 1
        assert result["results"][0]["results"] == []
        assert result["results"][0]["query"] == "nothing"
        assert "No news articles found" in result["summary"]

    def test_news_error_handling(self):
        """Provider errors should return a formatted error message."""
        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.search_news = AsyncMock(
                side_effect=ConnectionError("API unavailable")
            )

            result = search_fastsearch_news(queries=["test"])

        assert len(result["results"]) == 1
        assert result["results"][0]["results"] == []
        assert "FastSearch news search failed" in result["summary"]

    def test_news_partial_failure(self):
        """One failing news query should not prevent others from returning."""
        mock_results_q1 = [
            {
                "title": "Breaking News",
                "link": "https://example.com/news/1",
                "snippet": "A major event occurred today.",
                "source": "BBC News",
                "date": "2026-06-08T12:00:00Z",
            },
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.search_news = AsyncMock(side_effect=[
                mock_results_q1,
                ConnectionError("API unavailable"),
            ])

            result = search_fastsearch_news(
                queries=["breaking news", "broken query"],
            )

        assert len(result["results"]) == 2
        # First query succeeded
        assert result["results"][0]["query"] == "breaking news"
        assert len(result["results"][0]["results"]) == 1
        # Second query failed
        assert result["results"][1]["query"] == "broken query"
        assert result["results"][1]["results"] == []
        assert "Breaking News" in result["summary"]
        assert "FastSearch news search failed" in result["summary"]


class TestValidateSearchType:
    """Tests for the internal ``_validate_search_type`` helper."""

    def test_valid_types(self):
        """Known search types should not raise."""
        for st in ("all", "pages", "images", "news", "books"):
            _validate_search_type(st)  # Should not raise

    def test_invalid_type(self):
        """Unknown types should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown search_type"):
            _validate_search_type("invalid")

    def test_case_sensitive(self):
        """Types should be case-sensitive (lowercase)."""
        with pytest.raises(ValueError):
            _validate_search_type("ALL")

    def test_empty_string(self):
        """Empty string should raise ValueError."""
        with pytest.raises(ValueError):
            _validate_search_type("")


class TestTruncateBrief:
    """Unit tests for the ``_truncate_brief`` helper."""

    SHORT = "A short brief under any cap."
    CAP = 200

    def test_under_cap_passes_through_unchanged(self):
        """Brief shorter than cap is returned as-is."""
        result = _truncate_brief(self.SHORT, self.CAP)
        assert result == self.SHORT

    def test_exactly_at_cap_passes_through(self):
        """Brief exactly at cap length is returned as-is."""
        exact = "x" * self.CAP
        result = _truncate_brief(exact, self.CAP)
        assert result == exact

    def test_over_cap_truncated_at_paragraph(self):
        """Brief over cap is cut at the last paragraph break."""
        para1 = "First para. " * 6  # ~72 chars, well under 200 cap
        para2 = "Second paragraph. " * 20  # ~360 chars
        brief = para1.strip() + "\n\n" + para2.strip()
        result = _truncate_brief(brief, self.CAP)
        # Should end at the paragraph break, not mid-content.
        assert result.startswith(para1.strip())
        assert "truncated" in result.lower()
        assert len(result) <= self.CAP + 200  # room for truncation note

    def test_over_cap_falls_back_to_sentence(self):
        """When no paragraph break, falls back to sentence boundary."""
        sentences = (
            "First sentence with enough length to push past cap. "
            "Second sentence that is also long enough. "
            "Third sentence beyond the character limit here. "
            "Fourth sentence that should be fully cut off entirely. "
            "Fifth sentence more filler content text goes here. "
        )
        brief = sentences * 3  # ensure well over cap
        result = _truncate_brief(brief, self.CAP)
        assert "truncated" in result.lower()
        assert len(result) <= self.CAP + 200

    def test_over_cap_falls_back_to_word(self):
        """When no sentence break, falls back to word boundary."""
        # No periods/spaces in range — forces word-break fallback.
        brief = (
            "word " * 80 + "extra content beyond the cap " * 20
        )
        result = _truncate_brief(brief, self.CAP)
        assert "truncated" in result.lower()
        # Should not cut mid-word.
        assert not result.rstrip().endswith("extra")
        # Verify word boundary: truncated part properly ends at space.
        pre_note = result.split("\n\n---\n")[0]
        assert pre_note.endswith("word")

    def test_truncation_note_includes_char_counts(self):
        """The truncation note tells the model what happened."""
        brief = "Para one.\n\n" + ("Long paragraph content. " * 50)
        result = _truncate_brief(brief, self.CAP)
        assert "[Topic brief truncated at" in result
        assert "The full brief was" in result
        assert "characters" in result

    def test_under_cap_no_truncation_note(self):
        """No truncation note when brief fits within cap."""
        result = _truncate_brief(self.SHORT, 500)
        assert "truncated" not in result.lower()


class TestGetTopicBriefCap:
    """Integration tests for the size cap in ``get_topic_brief``."""

    QUERY = "latest news from Japan"
    CAP = 200  # small cap for fast tests

    @staticmethod
    def _mock_provider_response(brief, sources=None):
        """Build a mock provider that returns the given brief/sources."""
        if sources is None:
            sources = [
                {
                    "title": "Example Source",
                    "url": "https://example.com",
                }
            ]
        return {"brief": brief, "sources": sources,
                "confidence": "high", "cached": False}

    def test_brief_under_cap_passes_through(self):
        """Brief within the cap is returned unchanged in summary."""
        brief = "A short topic brief with some information."
        mock_result = self._mock_provider_response(brief)

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.get_topic_brief = AsyncMock(
                return_value=mock_result
            )
            with patch(
                "airunner_services.llm.safety."
                "search_rate_limiter.check_search_rate_limit",
                return_value=True,
            ), patch(
                "airunner_services.llm.safety."
                "account_context.get_current_account_id",
                return_value="test-account",
            ), patch(
                "extensions.fastsearch.server.tools."
                "_TOPIC_BRIEF_MAX_CHARS",
                200,
            ):
                result = get_topic_brief(
                    query=self.QUERY, max_sources=3
                )

        assert result["brief"] == brief
        assert result["confidence"] == "high"
        assert brief in result["summary"]

    def test_brief_over_cap_is_truncated(self):
        """Brief exceeding the cap is truncated in both fields."""
        brief = (
            "Paragraph one with some introductory content here. "
            "More content to make this longer. "
        ) * 10
        mock_result = self._mock_provider_response(brief)

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.get_topic_brief = AsyncMock(
                return_value=mock_result
            )
            with patch(
                "airunner_services.llm.safety."
                "search_rate_limiter.check_search_rate_limit",
                return_value=True,
            ), patch(
                "airunner_services.llm.safety."
                "account_context.get_current_account_id",
                return_value="test-account",
            ), patch(
                "extensions.fastsearch.server.tools."
                "_TOPIC_BRIEF_MAX_CHARS",
                200,
            ):
                result = get_topic_brief(
                    query=self.QUERY, max_sources=3
                )

        assert len(result["brief"]) <= self.CAP + 200
        assert "truncated" in result["brief"].lower()
        assert "truncated" in result["summary"].lower()
        assert result["confidence"] == "high"

    def test_truncation_respects_default_cap(self):
        """Without env override, the default 8000-char cap applies."""
        brief = "Short brief."  # well under 8000
        mock_result = self._mock_provider_response(brief)

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider:
            provider = mock_get_provider.return_value
            provider.get_topic_brief = AsyncMock(
                return_value=mock_result
            )
            with patch(
                "airunner_services.llm.safety."
                "search_rate_limiter.check_search_rate_limit",
                return_value=True,
            ), patch(
                "airunner_services.llm.safety."
                "account_context.get_current_account_id",
                return_value="test-account",
            ):
                result = get_topic_brief(
                    query=self.QUERY, max_sources=3
                )

        assert result["brief"] == brief
        assert "truncated" not in result["brief"].lower()


class TestSearchFastSearchMultiQueryCap:
    """Multi-query aggregate cap for ``search_fastsearch``."""

    def _make_mock_result(self, title="Result"):
        return [
            {
                "title": title,
                "link": "https://example.com",
                "snippet": "Snippet text. " * 20,
                "source": "Example",
                "date": "2026-01-01",
            }
        ]

    def test_single_query_unaffected(self):
        """A single query is always emitted, even if large."""
        large = self._make_mock_result("Large")
        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as m:
            m.return_value.search = AsyncMock(return_value=large)
            with patch(
                "airunner_services.llm.safety."
                "search_rate_limiter.check_search_rate_limit",
                return_value=True,
            ), patch(
                "airunner_services.llm.safety."
                "account_context.get_current_account_id",
                return_value="test-account",
            ), patch(
                "extensions.fastsearch.server."
                "search_result_capping."
                "_SEARCH_RESULTS_MAX_CHARS",
                200,
            ):
                result = search_fastsearch(queries=["single"])

        assert len(result["results"]) == 1
        assert "truncated" not in result["summary"].lower()

    def test_multi_query_under_cap_all_kept(self):
        """All queries kept when the total fits under the cap."""
        small = self._make_mock_result("Small")
        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as m:
            m.return_value.search = AsyncMock(return_value=small)
            with patch(
                "airunner_services.llm.safety."
                "search_rate_limiter.check_search_rate_limit",
                return_value=True,
            ), patch(
                "airunner_services.llm.safety."
                "account_context.get_current_account_id",
                return_value="test-account",
            ):
                result = search_fastsearch(
                    queries=["q1", "q2", "q3"]
                )

        assert len(result["results"]) == 3
        assert "truncated" not in result["summary"].lower()

    def test_multi_query_over_cap_trailing_dropped(self):
        """Trailing query blocks are dropped when cap exceeded."""
        small = self._make_mock_result("Small")
        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as m:
            m.return_value.search = AsyncMock(return_value=small)
            with patch(
                "airunner_services.llm.safety."
                "search_rate_limiter.check_search_rate_limit",
                return_value=True,
            ), patch(
                "airunner_services.llm.safety."
                "account_context.get_current_account_id",
                return_value="test-account",
            ), patch(
                "extensions.fastsearch.server."
                "search_result_capping."
                "_SEARCH_RESULTS_MAX_CHARS",
                200,
            ):
                result = search_fastsearch(
                    queries=["q1", "q2", "q3"]
                )

        assert len(result["results"]) < 3
        assert "truncated" in result["summary"].lower()
        assert "q2" in result["summary"]
        assert "q3" in result["summary"]


class TestSearchFastSearchNewsMultiQueryCap:
    """Multi-query aggregate cap for ``search_fastsearch_news``."""

    def _make_mock_result(self, title="News Result"):
        return [
            {
                "title": title,
                "link": "https://example.com/news",
                "snippet": "News snippet. " * 20,
                "source": "BBC",
                "date": "2026-01-01",
            }
        ]

    def test_single_query_unaffected(self):
        """A single news query is always emitted."""
        large = self._make_mock_result("Large News")
        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as m:
            m.return_value.search_news = AsyncMock(
                return_value=large
            )
            with patch(
                "airunner_services.llm.safety."
                "search_rate_limiter.check_search_rate_limit",
                return_value=True,
            ), patch(
                "airunner_services.llm.safety."
                "account_context.get_current_account_id",
                return_value="test-account",
            ), patch(
                "extensions.fastsearch.server."
                "search_result_capping."
                "_SEARCH_RESULTS_MAX_CHARS",
                200,
            ):
                result = search_fastsearch_news(
                    queries=["single news"]
                )

        assert len(result["results"]) == 1
        assert "truncated" not in result["summary"].lower()

    def test_multi_query_over_cap_trailing_dropped(self):
        """Trailing news query blocks dropped when cap exceeded."""
        small = self._make_mock_result("Small News")
        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as m:
            m.return_value.search_news = AsyncMock(
                return_value=small
            )
            with patch(
                "airunner_services.llm.safety."
                "search_rate_limiter.check_search_rate_limit",
                return_value=True,
            ), patch(
                "airunner_services.llm.safety."
                "account_context.get_current_account_id",
                return_value="test-account",
            ), patch(
                "extensions.fastsearch.server."
                "search_result_capping."
                "_SEARCH_RESULTS_MAX_CHARS",
                200,
            ):
                result = search_fastsearch_news(
                    queries=["n1", "n2", "n3"]
                )

        assert len(result["results"]) < 3
        assert "truncated" in result["summary"].lower()
        assert "Re-query individually" in result["summary"]
