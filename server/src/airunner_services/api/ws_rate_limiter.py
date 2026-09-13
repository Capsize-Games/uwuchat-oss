"""Per-account sliding-window rate limiter for WebSocket message dispatch.

WebSocket connections don't go through FastAPI's HTTP middleware, so
``slowapi`` (which decorates HTTP endpoints with a ``@limiter.limit``)
has no effect on WS message handlers.  This module provides a simple
per-account sliding-window counter that can be checked inside the WS
message-dispatch loop.

The rate limit is keyed on ``account_id`` (not IP) so shared-NAT users
are not penalised and a single account cannot hammer the LLM or RPC
handlers above the configured rate.  This mirrors the existing
``_MIN_REQUEST_INTERVAL`` pattern in ``llm_stream_routes.py`` but as a
reusable, testable module.
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock


class SlidingWindowRateLimiter:
    """Per-account sliding-window rate limiter.

    Tracks request timestamps per account in a sliding window of
    *window_seconds* and rejects requests that exceed *max_requests*.
    Thread-safe (``Lock``-protected).

    Usage::

        limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60)
        if not limiter.check(account_id):
            # Reject — account is over the rate limit.
            ...
    """

    def __init__(
        self, max_requests: int = 30, window_seconds: int = 60
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._buckets: dict[int | str, list[float]] = defaultdict(list)
        self._lock = Lock()

    @property
    def max_requests(self) -> int:
        """Maximum number of requests allowed per sliding window."""
        return self._max_requests

    @max_requests.setter
    def max_requests(self, value: int) -> None:
        with self._lock:
            self._max_requests = value

    @property
    def window_seconds(self) -> int:
        """Width of the sliding window in seconds."""
        return self._window_seconds

    @window_seconds.setter
    def window_seconds(self, value: int) -> None:
        with self._lock:
            self._window_seconds = value

    def check(self, key: int | str) -> bool:
        """Return ``True`` if *key* is within the rate limit.

        Records the check as a hit and prunes expired timestamps.
        Returns ``False`` when the key has exceeded ``max_requests``
        in the current sliding window.
        """
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            bucket = self._buckets[key]
            # Prune expired timestamps.
            self._buckets[key] = [t for t in bucket if t > cutoff]
            if len(self._buckets[key]) >= self._max_requests:
                return False
            self._buckets[key].append(now)
        return True

    def remaining(self, key: int | str) -> int:
        """Return how many requests *key* can still make in this window."""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        with self._lock:
            bucket = [t for t in self._buckets[key] if t > cutoff]
            return max(0, self._max_requests - len(bucket))

    def reset(self, key: int | str) -> None:
        """Clear all timestamps for *key* (e.g. on logout/disconnect)."""
        with self._lock:
            self._buckets.pop(key, None)

    def reset_all(self) -> None:
        """Clear all rate-limit state (e.g. for testing)."""
        with self._lock:
            self._buckets.clear()


# Default per-account rate limit for LLM streaming messages:
# 30 msg/min = one message every 2 seconds on average.
# This is generous enough for normal use (typing takes longer) but
# prevents a single account from saturating the LLM backend.
_LLM_STREAM_LIMITER = SlidingWindowRateLimiter(
    max_requests=30, window_seconds=60
)

# Default per-account rate limit for RPC operations:
# 120 calls/min = 2 per second.  The RPC path covers settings CRUD,
# conversation listing, and admin queries — bursts are expected (e.g.
# loading the conversation list on page load) so the limit is generous.
_RPC_LIMITER = SlidingWindowRateLimiter(
    max_requests=120, window_seconds=60
)


def check_llm_stream_rate(account_id: int | None) -> bool:
    """Check and record an LLM stream request against the per-account limit.

    Returns ``True`` if the request is allowed, ``False`` if rate-limited.
    When *account_id* is ``None`` (unauthenticated), the request is
    **rejected** — the caller must close the socket before reaching this
    point.
    """
    if account_id is None:
        return False
    return _LLM_STREAM_LIMITER.check(account_id)


def check_rpc_rate(account_id: int | None) -> bool:
    """Check and record an RPC request against the per-account limit.

    Returns ``True`` if the request is allowed, ``False`` if rate-limited.
    When *account_id* is ``None`` (unauthenticated), the request is
    **rejected** — the caller must close the socket before reaching this
    point.
    """
    if account_id is None:
        return False
    return _RPC_LIMITER.check(account_id)


def reset_account_limits(account_id: int | None) -> None:
    """Clear all rate-limit state for an account (e.g. on disconnect)."""
    if account_id is None:
        return
    _LLM_STREAM_LIMITER.reset(account_id)
    _RPC_LIMITER.reset(account_id)
