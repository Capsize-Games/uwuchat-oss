"""Tests for the shared WS per-account sliding-window rate limiter."""

from __future__ import annotations

import time


from airunner_services.api.ws_rate_limiter import (
    SlidingWindowRateLimiter,
    check_llm_stream_rate,
    check_rpc_rate,
    reset_account_limits,
)


class TestSlidingWindowRateLimiter:
    """Unit tests for the sliding-window rate limiter."""

    def test_allows_requests_within_limit(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert limiter.check("user1") is True

    def test_rejects_when_limit_exceeded(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.check("user1")
        assert limiter.check("user1") is False

    def test_different_keys_have_independent_counters(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
        for _ in range(2):
            limiter.check("user1")
        # user2 should still be allowed
        assert limiter.check("user2") is True

    def test_remaining_decreases_with_requests(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
        assert limiter.remaining("user1") == 5
        limiter.check("user1")
        assert limiter.remaining("user1") == 4

    def test_reset_clears_key(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
        limiter.check("user1")
        limiter.check("user1")
        assert limiter.check("user1") is False
        limiter.reset("user1")
        assert limiter.check("user1") is True

    def test_reset_all_clears_everything(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
        limiter.check("user1")
        limiter.check("user2")
        assert limiter.check("user1") is False
        limiter.reset_all()
        assert limiter.check("user1") is True
        assert limiter.check("user2") is True

    def test_window_slides_over_time(self) -> None:
        """Old entries expire after the window passes."""
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=0.1)
        limiter.check("user1")
        limiter.check("user1")
        assert limiter.check("user1") is False
        time.sleep(0.15)
        # After the window slides, the old entries are pruned
        assert limiter.check("user1") is True

    def test_none_key_is_rejected(self) -> None:
        """check_llm_stream_rate and check_rpc_rate reject None.

        Unauthenticated callers are rejected at connection time;
        reaching the rate limiter with account_id=None means the
        caller bypassed authentication and must be blocked.
        """
        assert check_llm_stream_rate(None) is False
        assert check_rpc_rate(None) is False

    def test_reset_account_limits_none_is_noop(self) -> None:
        """reset_account_limits(None) does not raise."""
        reset_account_limits(None)

    def test_reset_account_limits_restores_rpc_quota(self) -> None:
        """reset_account_limits clears the shared RPC bucket.

        Exhaust the module-level RPC limiter (120 requests/min), then
        assert a disconnect-time reset restores the full quota — this is
        the cleanup path wired into the WS event handler.
        """
        for _ in range(120):
            assert check_rpc_rate(9001) is True
        assert check_rpc_rate(9001) is False
        reset_account_limits(9001)
        assert check_rpc_rate(9001) is True

    def test_rejects_near_simultaneous_requests(self) -> None:
        """Burst of requests beyond limit is rejected."""
        limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=1)
        for _ in range(3):
            assert limiter.check("bursty")
        assert limiter.check("bursty") is False

    def test_max_requests_setter(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
        assert limiter.check("u") is True
        assert limiter.check("u") is False
        limiter.reset("u")
        limiter.max_requests = 2
        assert limiter.check("u") is True
        assert limiter.check("u") is True
        assert limiter.check("u") is False

    def test_window_seconds_setter(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=5, window_seconds=60)
        limiter.window_seconds = 0.05
        assert limiter.check("u") is True
        time.sleep(0.06)
        assert limiter.check("u") is True
