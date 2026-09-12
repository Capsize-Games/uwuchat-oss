"""Shared per-account rate limiter for search/scrape tool calls.

Used by both ``web_tools.py`` and ``extensions/fastsearch/server/tools.py``
to apply a sliding-window throttle keyed on ``account_id``.

Default: 10 calls per 60-second window per account.
Configurable via ``FASTSEARCH_RATE_LIMIT_MAX`` and
``FASTSEARCH_RATE_LIMIT_WINDOW`` environment variables.
"""

from __future__ import annotations

import os as _os

from airunner_services.api.ws_rate_limiter import (
    SlidingWindowRateLimiter,
)

_SEARCH_RATE_MAX = int(_os.environ.get("FASTSEARCH_RATE_LIMIT_MAX", "10"))
_SEARCH_RATE_WINDOW = int(
    _os.environ.get("FASTSEARCH_RATE_LIMIT_WINDOW", "60")
)

_limiter = SlidingWindowRateLimiter(
    max_requests=_SEARCH_RATE_MAX,
    window_seconds=_SEARCH_RATE_WINDOW,
)


def check_search_rate_limit(account_id: int | None) -> bool:
    """Check per-account search/scrape rate limit.

    Returns ``True`` if allowed, ``False`` if throttled.
    When *account_id* is ``None``, returns ``True``
    (graceful degradation — no context available).
    """
    if account_id is None:
        return True
    return _limiter.check(account_id)
