"""Transient network error classification and concise logging helpers.

All background LLM callers (mood, curiosity, compressor, world-tick, etc.)
use these to distinguish infrastructure blips from code bugs, log them
concisely at WARNING (no traceback), and optionally retry with backoff.
"""

from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Circuit breaker — stops background LLM calls when the API key
# is exhausted (403) or another permanent client error is detected.
# ------------------------------------------------------------------

#: Unix timestamp after which background calls may resume.
_api_exhausted_until: float = 0.0

#: Seconds to wait before retrying after a permanent API error.
_API_EXHAUSTION_COOLDOWN: float = 300.0  # 5 minutes


def is_api_exhausted() -> bool:
    """Return True when the API circuit breaker is open."""
    return time.time() < _api_exhausted_until


def mark_api_exhausted(exc: Optional[BaseException] = None) -> None:
    """Open the circuit breaker for the cooldown period.

    Call when a permanent client error (403, 401, etc.) is detected
    to prevent background tasks from wasting calls on an exhausted key.
    """
    global _api_exhausted_until
    _api_exhausted_until = time.time() + _API_EXHAUSTION_COOLDOWN
    if exc is not None:
        logger.warning(
            "API circuit breaker opened for %ds: %s",
            _API_EXHAUSTION_COOLDOWN,
            exc,
        )
    else:
        logger.warning(
            "API circuit breaker opened for %ds (manual)",
            _API_EXHAUSTION_COOLDOWN,
        )


_DEFAULT_MAX_RETRIES = 1
_DEFAULT_BACKOFF = 0.5  # seconds

# Lazy-imported tuple of exception types that indicate transient network
# failures (DNS, connection refused, timeout).
_TRANSIENT_EXCEPTIONS: Tuple[type, ...] | None = None


def _transient_exception_types() -> Tuple[type, ...]:
    """Lazily build and cache the set of transient network exception types."""
    global _TRANSIENT_EXCEPTIONS
    if _TRANSIENT_EXCEPTIONS is not None:
        return _TRANSIENT_EXCEPTIONS

    types: list[type] = []
    try:
        from httpx import ConnectError, TimeoutException
        types.extend([ConnectError, TimeoutException])
    except ImportError:
        pass
    try:
        from openai import APIConnectionError, APIError, APITimeoutError
        types.extend([APIConnectionError, APITimeoutError, APIError])
    except ImportError:
        pass
    try:
        from requests.exceptions import (
            ConnectionError as ReqConnError,
            Timeout as ReqTimeout,
        )
        types.extend([ReqConnError, ReqTimeout])
    except ImportError:
        pass
    try:
        from urllib3.exceptions import NameResolutionError
        types.append(NameResolutionError)
    except ImportError:
        pass
    try:
        from primp import ConnectError as PrimpConnectError
        types.append(PrimpConnectError)
    except ImportError:
        pass

    _TRANSIENT_EXCEPTIONS = tuple(types)
    return _TRANSIENT_EXCEPTIONS


def _extract_http_status(exc: BaseException) -> int | None:
    """Extract the HTTP status code from *exc* when available.

    Handles ``openai.APIStatusError`` (``.status_code``) and
    ``httpx.HTTPStatusError`` (``.response.status_code``).
    """
    try:
        from openai import APIStatusError
        if isinstance(exc, APIStatusError):
            return exc.status_code
    except ImportError:
        pass
    try:
        from httpx import HTTPStatusError
        if isinstance(exc, HTTPStatusError):
            return exc.response.status_code
    except ImportError:
        pass
    return None


def _is_permanent_client_error(status_code: int) -> bool:
    """Return True when *status_code* is a 4xx error that will not heal
    on retry (excludes 408 Request Timeout and 429 Too Many Requests)."""
    if status_code < 400 or status_code >= 500:
        return False
    if status_code in (408, 429):
        return False
    return True


def is_permanent_client_error(exc: BaseException) -> bool:
    """Return True when *exc* is a permanent 4xx client error.

    Permanent errors (401, 403, 404, etc.) will never succeed on retry.
    Uses the same logic as _is_permanent_client_error but accepts an
    exception object for convenience.
    """
    status = _extract_http_status(exc)
    if status is None:
        return False
    return _is_permanent_client_error(status)


def is_http_service_error(exc: BaseException) -> bool:
    """Return True when *exc* is an HTTP status error (4xx/5xx)."""
    try:
        from requests.exceptions import HTTPError
        if isinstance(exc, HTTPError):
            return True
    except ImportError:
        pass
    try:
        from httpx import HTTPStatusError
        if isinstance(exc, HTTPStatusError):
            return True
    except ImportError:
        pass
    return False


def is_transient_network_error(exc: BaseException) -> bool:
    """Return True when *exc* is a known transient network error.

    Also checks the exception cause chain (``__cause__``) so that
    library wrapper exceptions (e.g. ``DuckDuckGoSearchException``
    wrapping ``primp.ConnectError``) are recognized.

    Permanent client errors (401, 402, 403, 404, etc.) are never
    considered transient — retrying them is pointless.
    """
    status = _extract_http_status(exc)
    if status is not None and _is_permanent_client_error(status):
        return False
    transient = _transient_exception_types()
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, transient):
            return True
        current = current.__cause__
    return False


def extract_user_error_message(exc: BaseException) -> str | None:
    """Extract a user-safe error message from an API exception.

    Returns ``None`` when no structured message is available, so
    callers can fall back to a generic message of their choice.
    Strips URLs from the error text to avoid leaking key hashes.
    """
    try:
        from openai import APIStatusError
        if isinstance(exc, APIStatusError):
            body = getattr(exc, "body", None)
            if isinstance(body, dict):
                error = body.get("error", {})
                if isinstance(error, dict):
                    msg = error.get("message", "")
                    if msg:
                        import re
                        return re.sub(r"https?://\S+", "", msg).strip()
    except ImportError:
        pass
    return None


def log_network_failure(
    logger_obj: logging.Logger,
    context: str,
    exc: BaseException,
) -> None:
    """Log a concise warning for a network failure (no traceback)."""
    logger_obj.warning("%s: %s", context, exc)


def log_network_error_diagnostic(
    logger_obj: logging.Logger,
    context: str,
    exc: BaseException,
) -> None:
    """Log detailed diagnostics for a network error at ERROR level.

    Captures the exception type, chained cause, and target host (when
    available from an httpx request error) so developers can
    distinguish DNS failures from connection-refused from TLS errors
    from timeouts — all of which stringify similarly.
    """
    exc_type = type(exc).__name__
    parts = [f"{context}: {exc_type}: {exc}"]
    _append_cause_info(parts, exc)
    _append_target_host(parts, exc)
    logger_obj.error(" | ".join(parts))


def _append_cause_info(parts: list, exc: BaseException) -> None:
    """Append chained-cause type and message when available."""
    cause = exc.__cause__ or exc.__context__
    if cause is None:
        return
    cause_type = type(cause).__name__
    cause_msg = str(cause)
    parts.append(f"cause={cause_type}: {cause_msg}")


def _append_target_host(parts: list, exc: BaseException) -> None:
    """Append the target host (scheme+host only) from an httpx error.

    Checks both the exception itself (for raw/unwrapped httpx errors
    like ConnectError/TimeoutException) and the chained cause (for
    library-wrapper errors raised via ``raise ... from err``).
    """
    try:
        from httpx import RequestError
    except ImportError:
        return
    candidates = [exc]
    cause = exc.__cause__ or exc.__context__
    if cause is not None:
        candidates.append(cause)
    for candidate in candidates:
        if not isinstance(candidate, RequestError):
            continue
        req = getattr(candidate, "request", None)
        if req is None:
            continue
        url = getattr(req, "url", None)
        if url is None:
            continue
        from urllib.parse import urlparse
        parsed = urlparse(str(url))
        parts.append(f"host={parsed.scheme}://{parsed.netloc}")
        return


def is_dns_resolution_error(exc: BaseException) -> bool:
    """Return True when *exc* (or its cause chain) is a DNS resolution failure.

    DNS failures inside containers behind a VPN (e.g. Mullvad) are a
    specific failure mode: the host resolver IP changed after the
    container was created, leaving it with a stale DNS forwarder.
    Callers can use this to distinguish "DNS is broken, re-run
    scripts/docker.sh" from a generic transient network error.

    Walks both ``__cause__`` and ``__context__`` because ``requests``
    / ``urllib3`` set ``__context__`` (automatic chaining), not
    ``__cause__`` (explicit ``raise ... from ...``), on connection
    errors.
    """
    try:
        from urllib3.exceptions import NameResolutionError
        _target = (NameResolutionError,)
    except ImportError:
        return False

    seen: set[int] = set()
    stack: list[BaseException | None] = [exc]
    while stack:
        current = stack.pop()
        if current is None:
            continue
        cid = id(current)
        if cid in seen:
            continue
        seen.add(cid)
        if isinstance(current, _target):
            return True
        stack.append(current.__cause__)
        stack.append(current.__context__)
    return False


def log_dns_failure_warning(logger_obj: logging.Logger) -> None:
    """Log a loud, actionable warning about a probable stale-DNS condition.

    Call this when an outbound HTTP call fails with a DNS resolution
    error — it logs at ERROR level with a clear remediation message
    that the developer can grep for.
    """
    logger_obj.error(
        "DNS RESOLUTION FAILURE — the container cannot resolve external "
        "hosts.  This usually means the host DNS resolver changed "
        "(e.g. Mullvad relay switch) after the container was created.  "
        "Re-run: ./scripts/docker.sh recreate server"
    )


def retry_on_network(
    max_retries: int = _DEFAULT_MAX_RETRIES,
    backoff: float = _DEFAULT_BACKOFF,
):
    """Decorator that retries on transient network errors with backoff.

    Non-network exceptions are re-raised immediately so callers can
    handle them separately.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exc: BaseException | None = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:
                    if not is_transient_network_error(exc):
                        raise
                    last_exc = exc
                    if attempt < max_retries:
                        delay = backoff * (2 ** attempt)
                        time.sleep(delay)
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator
