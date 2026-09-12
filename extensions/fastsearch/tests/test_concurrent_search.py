"""Tests for bounded-concurrency search execution with retry.

These tests mock the provider to return controlled delays and
failures so we can assert:
- Concurrent queries complete faster than sequential
- Concurrency is bounded
- HTTP 502 triggers one retry, then fails gracefully
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from extensions.fastsearch.server.concurrent_search import (
    CONCURRENCY_LIMIT,
    is_transient_http_error,
    retry_call,
)
from extensions.fastsearch.server.tools import (
    _execute_concurrent_queries,
    _process_search_results,
)


# ------------------------------------------------------------------
# retry_call
# ------------------------------------------------------------------


class TestRetryCall:
    """Tests for ``retry_call`` transient-HTTP-error retry logic."""

    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        """Successful call returns immediately without retry."""
        call_count = 0

        async def _ok():
            nonlocal call_count
            call_count += 1
            return "result"

        result = await retry_call(_ok, "test")
        assert result == "result"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_transient_502_retried_once(self):
        """HTTP 502 triggers one retry, then succeeds."""
        call_count = 0

        async def _flaky():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise aiohttp.ClientResponseError(
                    request_info=None,
                    history=(),
                    status=502,
                    message="Bad Gateway",
                    headers={},
                )
            return "recovered"

        result = await retry_call(_flaky, "test")
        assert result == "recovered"
        assert call_count == 2  # initial + one retry

    @pytest.mark.asyncio
    async def test_transient_503_retried_then_fails(self):
        """Persistent 503 fails after exhausting retries."""
        async def _always_503():
            raise aiohttp.ClientResponseError(
                request_info=None,
                history=(),
                status=503,
                message="Service Unavailable",
                headers={},
            )

        with pytest.raises(aiohttp.ClientResponseError) as exc_info:
            await retry_call(_always_503, "test")
        assert exc_info.value.status == 503

    @pytest.mark.asyncio
    async def test_client_4xx_not_retried(self):
        """HTTP 400/401/403/404 are NOT retried."""
        call_count = 0

        async def _bad_request():
            nonlocal call_count
            call_count += 1
            raise aiohttp.ClientResponseError(
                request_info=None,
                history=(),
                status=400,
                message="Bad Request",
                headers={},
            )

        with pytest.raises(aiohttp.ClientResponseError) as exc_info:
            await retry_call(_bad_request, "test")
        assert exc_info.value.status == 400
        assert call_count == 1  # no retry

    @pytest.mark.asyncio
    async def test_connection_error_not_retried(self):
        """Non-HTTP errors (ConnectionError) propagate immediately."""
        call_count = 0

        async def _conn_err():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("network down")

        with pytest.raises(ConnectionError):
            await retry_call(_conn_err, "test")
        assert call_count == 1  # no retry


# ------------------------------------------------------------------
# is_transient_http_error
# ------------------------------------------------------------------


class TestIsTransientHttpError:
    """Tests for ``is_transient_http_error``."""

    def test_502_is_transient(self):
        exc = aiohttp.ClientResponseError(
            request_info=None, history=(),
            status=502, message="Bad Gateway", headers={},
        )
        assert is_transient_http_error(exc) is True

    def test_503_is_transient(self):
        exc = aiohttp.ClientResponseError(
            request_info=None, history=(),
            status=503, message="Service Unavailable", headers={},
        )
        assert is_transient_http_error(exc) is True

    def test_504_is_transient(self):
        exc = aiohttp.ClientResponseError(
            request_info=None, history=(),
            status=504, message="Gateway Timeout", headers={},
        )
        assert is_transient_http_error(exc) is True

    def test_500_not_transient(self):
        exc = aiohttp.ClientResponseError(
            request_info=None, history=(),
            status=500, message="Internal Server Error", headers={},
        )
        assert is_transient_http_error(exc) is False

    def test_non_http_error_not_transient(self):
        assert is_transient_http_error(ConnectionError()) is False
        assert is_transient_http_error(ValueError()) is False


# ------------------------------------------------------------------
# Concurrent execution — wall-clock improvement
# ------------------------------------------------------------------


_DELAY = 0.05  # artificial delay per query


async def _slow_query(query: str, session) -> list[dict]:
    """Mock provider that introduces a fixed delay per query."""
    await asyncio.sleep(_DELAY)
    return [{"title": f"Result for {query}", "link": "#",
             "snippet": f"Snippet for {query}"}]


class TestConcurrentWallClock:
    """Tests verifying concurrent queries are faster than sequential."""

    QUERIES = ["q1", "q2", "q3", "q4"]

    def test_concurrent_faster_than_sequential(self):
        """4 queries @ 50 ms each: concurrent ~50 ms, sequential ~200 ms."""
        t0 = time.monotonic()
        raw = asyncio.run(
            _execute_concurrent_queries(self.QUERIES, _slow_query)
        )
        elapsed = time.monotonic() - t0

        # Results: all 4 queries should succeed.
        assert len(raw) == len(self.QUERIES)
        for q, result in raw:
            assert not isinstance(result, BaseException), (
                f"Query {q} failed: {result}"
            )

        # Concurrent should complete in roughly one delay + overhead,
        # NOT delay * count (which would be ~0.20+ seconds).
        sequential_minimum = _DELAY * len(self.QUERIES)  # ~0.20
        assert elapsed < sequential_minimum * 0.75, (
            f"Concurrent elapsed {elapsed:.3f}s but sequential "
            f"lower bound is {sequential_minimum:.3f}s — "
            f"concurrency is not working"
        )

    def test_results_maintain_order(self):
        """Results list preserves input query order."""
        raw = asyncio.run(
            _execute_concurrent_queries(self.QUERIES, _slow_query)
        )
        for (q, _), expected in zip(raw, self.QUERIES):
            assert q == expected

    def test_partial_failure_does_not_block_batch(self):
        """One query raising 502 does not prevent others from returning."""
        call_counts: dict[str, int] = {}

        async def _flaky_or_slow(query: str, session) -> list[dict]:
            call_counts[query] = call_counts.get(query, 0) + 1
            if query == "bad" and call_counts[query] <= 1:
                # simulate 502 on first attempt; retry_call will retry
                raise aiohttp.ClientResponseError(
                    request_info=None, history=(),
                    status=502, message="Bad Gateway", headers={},
                )
            await asyncio.sleep(0.01)
            return [{"title": f"Result for {query}", "link": "#",
                     "snippet": ""}]

        raw = asyncio.run(
            _execute_concurrent_queries(["good1", "bad", "good2"],
                                        _flaky_or_slow)
        )

        # "bad" should succeed on retry (2nd attempt = call_count 2)
        assert len(raw) == 3
        for q, result in raw:
            if q == "bad":
                assert not isinstance(result, BaseException), (
                    f"bad query failed: {result}"
                )


# ------------------------------------------------------------------
# Concurrency boundedness
# ------------------------------------------------------------------


class TestConcurrencyBounded:
    """Verify that the semaphore enforces ``CONCURRENCY_LIMIT``."""

    async def _tracked_query(
        self,
        query: str,
        session,
        tracker: dict,
    ) -> list[dict]:
        """Increment in-flight counter, sleep, decrement."""
        tracker["in_flight"] = tracker.get("in_flight", 0) + 1
        tracker["max_seen"] = max(
            tracker.get("max_seen", 0), tracker["in_flight"]
        )
        await asyncio.sleep(0.02)
        tracker["in_flight"] -= 1
        return [{"title": query, "link": "#", "snippet": ""}]

    def test_concurrency_is_bounded(self):
        """Max in-flight never exceeds CONCURRENCY_LIMIT."""
        import functools

        tracker: dict = {}
        queries = [f"q{i}" for i in range(6)]  # more than CONCURRENCY_LIMIT

        raw = asyncio.run(
            _execute_concurrent_queries(
                queries,
                functools.partial(
                    self._tracked_query, tracker=tracker,
                ),
            )
        )

        assert len(raw) == len(queries)
        max_seen = tracker.get("max_seen", 0)
        assert max_seen <= CONCURRENCY_LIMIT, (
            f"Max in-flight {max_seen} exceeds "
            f"CONCURRENCY_LIMIT {CONCURRENCY_LIMIT}"
        )
        assert max_seen > 1, (
            "Concurrency never exceeded 1 — bounded but not actually "
            "concurrent"
        )


# ------------------------------------------------------------------
# _process_search_results
# ------------------------------------------------------------------


class TestProcessSearchResults:
    """Tests for ``_process_search_results`` post-processing."""

    def test_success_results_formatted(self):
        """Valid results produce formatted output."""
        raw = [
            ("q1", [{"title": "T1", "link": "#", "snippet": "S1"}]),
        ]
        per_query, formatted = _process_search_results(
            raw, "all", "search_fastsearch"
        )
        assert len(per_query) == 1
        assert per_query[0]["query"] == "q1"
        assert len(per_query[0]["results"]) == 1
        assert "T1" in formatted[0]

    def test_exception_results_error_message(self):
        """Exception results produce error entries."""
        raw = [
            ("q1", ConnectionError("down")),
        ]
        per_query, formatted = _process_search_results(
            raw, "all", "search_fastsearch"
        )
        assert len(per_query) == 1
        assert per_query[0]["results"] == []
        assert "failed" in formatted[0]

    def test_empty_results_no_results_message(self):
        """Empty list produces 'no results' message."""
        raw = [("q1", [])]
        per_query, formatted = _process_search_results(
            raw, "all", "search_fastsearch"
        )
        assert len(per_query) == 1
        assert per_query[0]["results"] == []
        assert "No results found" in formatted[0]


# ------------------------------------------------------------------
# Regression: per-query rate-limit consumption
# ------------------------------------------------------------------


class TestPerQueryRateLimit:
    """Regression: N queries consume N rate-limit slots, not 1."""

    def test_n_queries_consume_n_slots(self):
        """3 accepted queries = 3 calls to check_search_rate_limit."""
        from unittest.mock import AsyncMock, patch

        call_count = 0

        def _counting_check(_account_id):
            nonlocal call_count
            call_count += 1
            # Allow first 2 queries; third hits the limit.
            return call_count <= 2

        mock_results = [
            {"title": "Result", "link": "#", "snippet": "S"}
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider, patch(
            "airunner_services.llm.safety."
            "search_rate_limiter.check_search_rate_limit",
            side_effect=_counting_check,
        ), patch(
            "airunner_services.llm.safety."
            "account_context.get_current_account_id",
            return_value="test-account",
        ):
            provider = mock_get_provider.return_value
            provider.search = AsyncMock(return_value=mock_results)

            from extensions.fastsearch.server.tools import (
                search_fastsearch,
            )
            result = search_fastsearch(
                queries=["q1", "q2", "q3"],
                search_type="all",
                num_results=10,
            )

        # 3 queries → 3 rate-limit checks consumed.
        assert call_count == 3, (
            f"Expected 3 rate-limit checks for 3 queries, "
            f"got {call_count}"
        )

        # q1 and q2 should succeed; q3 should be rate-limited.
        assert len(result["results"]) == 3
        assert result["results"][0]["query"] == "q1"
        assert len(result["results"][0]["results"]) == 1
        assert result["results"][1]["query"] == "q2"
        assert len(result["results"][1]["results"]) == 1
        assert result["results"][2]["query"] == "q3"
        assert result["results"][2]["results"] == []
        assert "rate limit" in result["summary"].lower()


class TestPerQueryRateLimitNews:
    """Regression: N news queries consume N rate-limit slots."""

    def test_n_news_queries_consume_n_slots(self):
        """Same as above but for search_fastsearch_news."""
        from unittest.mock import AsyncMock, patch

        call_count = 0

        def _counting_check(_account_id):
            nonlocal call_count
            call_count += 1
            return call_count <= 1

        mock_results = [
            {
                "title": "News", "link": "#",
                "snippet": "S", "source": "BBC",
                "date": "2026-01-01",
            }
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider, patch(
            "airunner_services.llm.safety."
            "search_rate_limiter.check_search_rate_limit",
            side_effect=_counting_check,
        ), patch(
            "airunner_services.llm.safety."
            "account_context.get_current_account_id",
            return_value="test-account",
        ):
            provider = mock_get_provider.return_value
            provider.search_news = AsyncMock(return_value=mock_results)

            from extensions.fastsearch.server.tools import (
                search_fastsearch_news,
            )
            result = search_fastsearch_news(
                queries=["news1", "news2"],
                num_results=10,
            )

        assert call_count == 2, (
            f"Expected 2 rate-limit checks, got {call_count}"
        )
        assert len(result["results"]) == 2
        assert result["results"][0]["query"] == "news1"
        assert len(result["results"][0]["results"]) == 1
        assert result["results"][1]["query"] == "news2"
        assert result["results"][1]["results"] == []


# ------------------------------------------------------------------
# Regression: query_map dict collision (fix #3)
# ------------------------------------------------------------------


class TestNewsQuerySanitizationCollision:
    """Regression: two queries that sanitize to the same string
    each keep their own original label."""

    def _make_news_result(self):
        return [
            {
                "title": "News", "link": "#",
                "snippet": "S", "source": "BBC",
                "date": "2026-01-01",
            }
        ]

    def test_sanitization_collision_preserves_labels(self):
        """Queries differing only in trailing dates keep original labels."""
        from unittest.mock import AsyncMock, patch

        mock_results = self._make_news_result()

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider, patch(
            "airunner_services.llm.safety."
            "search_rate_limiter.check_search_rate_limit",
            return_value=True,
        ), patch(
            "airunner_services.llm.safety."
            "account_context.get_current_account_id",
            return_value="test-account",
        ):
            provider = mock_get_provider.return_value
            provider.search_news = AsyncMock(
                return_value=mock_results,
            )

            from extensions.fastsearch.server.tools import (
                search_fastsearch_news,
            )
            result = search_fastsearch_news(
                queries=[
                    "election results 2026-07-01",
                    "election results today July 1 2026",
                ],
                num_results=10,
            )

        # Both queries strip to the same sanitized form, but each
        # result entry must keep its OWN original label.
        assert len(result["results"]) == 2
        assert (
            result["results"][0]["query"]
            == "election results 2026-07-01"
        )
        assert (
            result["results"][1]["query"]
            == "election results today July 1 2026"
        )
        # Both should have results (provider returned same list each time).
        assert len(result["results"][0]["results"]) == 1
        assert len(result["results"][1]["results"]) == 1


# ------------------------------------------------------------------
# Regression: duplicate query string collision (fix #2 follow-up)
# ------------------------------------------------------------------


class TestDuplicateQueryCollision:
    """Regression: identical query strings in one batch must not
    silently overwrite each other in the result assembly."""

    def test_duplicate_queries_preserve_distinct_results(self):
        """Two identical query strings each return their own result."""
        from unittest.mock import AsyncMock, patch

        result_a = [
            {"title": "Result A", "link": "#a", "snippet": "A"}
        ]
        result_b = [
            {"title": "Result B", "link": "#b", "snippet": "B"}
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider, patch(
            "airunner_services.llm.safety."
            "search_rate_limiter.check_search_rate_limit",
            return_value=True,
        ), patch(
            "airunner_services.llm.safety."
            "account_context.get_current_account_id",
            return_value="test-account",
        ):
            provider = mock_get_provider.return_value
            provider.search = AsyncMock(
                side_effect=[result_a, result_b],
            )

            from extensions.fastsearch.server.tools import (
                search_fastsearch,
            )
            result = search_fastsearch(
                queries=["same query", "same query"],
                search_type="all",
                num_results=10,
            )

        # Both result entries must appear; each with its own distinct
        # mocked result, not both showing the second one.
        assert len(result["results"]) == 2
        assert (
            result["results"][0]["query"] == "same query"
        )
        assert (
            result["results"][1]["query"] == "same query"
        )
        # First entry → Result A.
        assert (
            result["results"][0]["results"][0]["title"]
            == "Result A"
        ), (
            "Expected 'Result A' at position 0, got "
            f"{result['results'][0]['results']}"
        )
        # Second entry → Result B (not a duplicate of A).
        assert (
            result["results"][1]["results"][0]["title"]
            == "Result B"
        ), (
            "Expected 'Result B' at position 1, got "
            f"{result['results'][1]['results']}"
        )


# ------------------------------------------------------------------
# Regression: search_type default changed to "pages" (Issue 1)
# ------------------------------------------------------------------


class TestSearchTypeDefault:
    """Verify ``search_fastsearch`` defaults to ``pages``, not ``all``."""

    def test_default_sends_pages(self):
        """Without an explicit search_type, provider.search receives
        search_type='pages'."""
        from unittest.mock import AsyncMock, patch

        mock_results = [
            {"title": "Result", "link": "#", "snippet": "S"}
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider, patch(
            "airunner_services.llm.safety."
            "search_rate_limiter.check_search_rate_limit",
            return_value=True,
        ), patch(
            "airunner_services.llm.safety."
            "account_context.get_current_account_id",
            return_value="test-account",
        ):
            provider = mock_get_provider.return_value
            provider.search = AsyncMock(return_value=mock_results)

            from extensions.fastsearch.server.tools import (
                search_fastsearch,
            )
            search_fastsearch(queries=["test"])

        # Verify provider.search was called with search_type="pages".
        provider.search.assert_called_once()
        _, kwargs = provider.search.call_args
        assert kwargs["search_type"] == "pages", (
            f"Expected search_type='pages' (new default), "
            f"got {kwargs.get('search_type')!r}"
        )

    def test_explicit_all_still_works(self):
        """Explicit search_type='all' is passed through unchanged."""
        from unittest.mock import AsyncMock, patch

        mock_results = [
            {"title": "Result", "link": "#", "snippet": "S"}
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider, patch(
            "airunner_services.llm.safety."
            "search_rate_limiter.check_search_rate_limit",
            return_value=True,
        ), patch(
            "airunner_services.llm.safety."
            "account_context.get_current_account_id",
            return_value="test-account",
        ):
            provider = mock_get_provider.return_value
            provider.search = AsyncMock(return_value=mock_results)

            from extensions.fastsearch.server.tools import (
                search_fastsearch,
            )
            search_fastsearch(queries=["test"], search_type="all")

        provider.search.assert_called_once()
        _, kwargs = provider.search.call_args
        assert kwargs["search_type"] == "all", (
            f"Expected search_type='all' (explicit), "
            f"got {kwargs.get('search_type')!r}"
        )

    def test_explicit_images_still_works(self):
        """Explicit search_type='images' is passed through."""
        from unittest.mock import AsyncMock, patch

        mock_results = [
            {"title": "Image", "link": "#", "snippet": "img"}
        ]

        with patch(
            "extensions.fastsearch.server.tools._get_provider"
        ) as mock_get_provider, patch(
            "airunner_services.llm.safety."
            "search_rate_limiter.check_search_rate_limit",
            return_value=True,
        ), patch(
            "airunner_services.llm.safety."
            "account_context.get_current_account_id",
            return_value="test-account",
        ):
            provider = mock_get_provider.return_value
            provider.search = AsyncMock(return_value=mock_results)

            from extensions.fastsearch.server.tools import (
                search_fastsearch,
            )
            search_fastsearch(queries=["test"], search_type="images")

        provider.search.assert_called_once()
        _, kwargs = provider.search.call_args
        assert kwargs["search_type"] == "images"


# ------------------------------------------------------------------
# Load-test error classification (load_test.py _report logic)
# ------------------------------------------------------------------


class TestLoadTestErrorClassification:
    """Verify that non-2xx statuses are classified as errors."""

    @staticmethod
    def _classify(
        results: list[tuple[str, float, int | None, str | None]],
    ) -> tuple[list, list]:
        """Replicate the error classification from load_test.py."""
        errors = [
            r for r in results if r[2] is None or r[2] >= 400
        ]
        transient = [r for r in errors if r[2] in (502, 503, 504)]
        return errors, transient

    def test_200s_not_errors(self):
        results = [
            ("/api/search/", 1.0, 200, None),
            ("/api/search/", 2.0, 200, None),
        ]
        errors, transient = self._classify(results)
        assert len(errors) == 0
        assert len(transient) == 0

    def test_401_is_error(self):
        results = [
            ("/api/search/", 0.01, 401, None),
        ]
        errors, transient = self._classify(results)
        assert len(errors) == 1
        assert len(transient) == 0

    def test_404_is_error(self):
        results = [
            ("/api/search/", 0.01, 404, None),
        ]
        errors, transient = self._classify(results)
        assert len(errors) == 1
        assert len(transient) == 0

    def test_500_is_error(self):
        results = [
            ("/api/search/", 1.0, 500, None),
        ]
        errors, transient = self._classify(results)
        assert len(errors) == 1
        assert not transient  # 500 is not transient

    def test_502_is_transient_error(self):
        results = [
            ("/api/search/", 1.0, 502, None),
        ]
        errors, transient = self._classify(results)
        assert len(errors) == 1
        assert len(transient) == 1

    def test_none_status_is_error(self):
        """Connection dropped → status is None → error."""
        results = [
            ("/api/search/", 5.0, None, "timeout"),
        ]
        errors, transient = self._classify(results)
        assert len(errors) == 1
        assert len(transient) == 0

    def test_mixed_statuses(self):
        """Only 200s are successes; 4xx and 5xx are errors."""
        results = [
            ("/api/search/", 1.0, 200, None),
            ("/api/search/", 0.1, 401, None),
            ("/api/search/", 0.1, 404, None),
            ("/api/search/", 1.0, 500, None),
            ("/api/search/", 1.0, 502, None),
        ]
        errors, transient = self._classify(results)
        assert len(errors) == 4  # 401, 404, 500, 502
        assert len(transient) == 1  # only 502
