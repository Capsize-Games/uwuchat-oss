"""Retry-with-backoff and concurrency constants for FastSearch queries.

Used by ``tools.py`` to replace the sequential per-query loop with
bounded-concurrent execution under a single event loop.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Callable, Coroutine, TypeVar

import aiohttp

from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application.get_logger import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

# Maximum concurrent FastSearch requests per tool call.
# Default 2 — conservative for the current 2-vCPU shared instance;
# raise when FastSearch moves to dedicated hardware.
CONCURRENCY_LIMIT = int(
    os.getenv("FASTSEARCH_CONCURRENCY_LIMIT", "2")
)

# Maximum retry attempts per query for transient upstream failures
# (HTTP 502, 503, 504).  Default 2 = one initial attempt + one retry.
RETRY_MAX_ATTEMPTS = int(
    os.getenv("FASTSEARCH_RETRY_MAX_ATTEMPTS", "2")
)

# Base delay in seconds for exponential backoff (doubles each retry).
RETRY_BASE_DELAY = float(
    os.getenv("FASTSEARCH_RETRY_BASE_DELAY", "1.0")
)

# HTTP status codes treated as transient (trigger a retry, not an
# immediate failure).
TRANSIENT_STATUSES: frozenset[int] = frozenset({502, 503, 504})

T = TypeVar("T")


def is_transient_http_error(exc: BaseException) -> bool:
    """Return True when *exc* is a retryable upstream HTTP error."""
    if not isinstance(exc, aiohttp.ClientResponseError):
        return False
    return exc.status in TRANSIENT_STATUSES


async def retry_call(
    coro_factory: Callable[[], Coroutine[Any, Any, T]],
    query_label: str = "",
) -> T:
    """Call *coro_factory*, retrying on transient HTTP 502/503/504.

    *coro_factory* is a zero-arg callable returning a fresh coroutine
    each time — necessary because a coroutine can only be awaited once.

    Retries up to ``RETRY_MAX_ATTEMPTS - 1`` times with exponential
    backoff.  Non-transient errors (4xx, network failures, timeouts)
    propagate immediately without retry.
    """
    if RETRY_MAX_ATTEMPTS < 1:
        return await coro_factory()

    last_exc: BaseException | None = None
    for attempt in range(1, RETRY_MAX_ATTEMPTS + 1):
        try:
            return await coro_factory()
        except aiohttp.ClientResponseError as exc:
            last_exc = exc
            if not is_transient_http_error(exc):
                raise
            logger.warning(
                "FastSearch transient HTTP %s on query '%s' "
                "(attempt %d/%d)",
                exc.status,
                query_label[:80],
                attempt,
                RETRY_MAX_ATTEMPTS,
            )
            if attempt < RETRY_MAX_ATTEMPTS:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

    # All attempts exhausted — re-raise the last transient error.
    raise last_exc  # type: ignore[misc]
