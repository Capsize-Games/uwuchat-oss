"""Completion-path choke point — admission control + retry for OpenRouter.

Every chat/completion call must route through this module instead of
calling ``model.invoke()`` / ``model.stream()`` directly.  This is the
completion-path equivalent of ``embedding_provider.py::_call_api`` for
the embedding path — it didn't exist before this work, and creating it
is part of the distributed-priority-lane plan.

Usage::

    from airunner_services.cloud.llm.completion_choke import (
        invoke_with_limiter,
    )

    response = invoke_with_limiter(
        model, messages,
        priority="bulk",
        tenant_key="tenant_xyz",
    )

See ``plans/uwuchat-embedding-rate-limit-priority-lanes.md`` for the
full design rationale.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Iterator, Literal

logger = logging.getLogger(__name__)

# Transient failures (rate limiting, provider-side overload) must not
# be treated as permanent.  Retried with exponential backoff + jitter
# — mirroring ``embedding_provider.py``'s retry logic, since none
# existed on the completion path before this work.
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 30.0

# How long a live-lane caller waits for a slot before degrading.
_LIVE_WAIT_MAX_SECONDS = 3.0
_LIVE_WAIT_POLL_SECONDS = 0.25


class LiveLaneExhaustedError(RuntimeError):
    """Raised when the live completion lane has no available slots.

    Caught by ``_attempt_stream`` and ``generate_response`` in the
    live DIALOGUE path to produce a user-visible "busy, try again"
    message instead of a silent ``None`` return.
    """


def _is_retryable_error(exc: Exception) -> bool:
    """Return True if *exc* looks like a transient error worth retrying.

    Checks the exception chain (``__cause__``, ``__context__``) and
    string representation for HTTP 429/5xx, rate-limit, overload,
    and connection-timeout markers.  The existing
    ``is_transient_network_error`` utility from
    ``airunner_services.utils.network_retry`` is consulted first for
    typed exceptions (e.g. ``openai.RateLimitError``); this fallback
    catches plain ``Exception`` wrappers that carry the status code
    or message in args.
    """
    # Try the typed detector first (handles openai.RateLimitError etc.)
    try:
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
        )
        if is_transient_network_error(exc):
            return True
    except Exception:
        pass

    # Walk the exception chain and check string representations.
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None:
        eid = id(current)
        if eid in seen:
            break
        seen.add(eid)
        text = (
            str(current)
            + " ".join(str(a) for a in getattr(current, "args", []))
        ).lower()
        if any(
            word in text
            for word in (
                "429", "rate limit", "rate_limit", "overloaded",
                "503", "502", "504", "timeout", "connection",
            )
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


def _sleep_before_retry(attempt: int, exc: Exception) -> None:
    """Exponential backoff with jitter, capped."""
    delay = _BACKOFF_BASE_SECONDS * (2 ** attempt)
    delay = min(delay, _BACKOFF_MAX_SECONDS)
    delay += random.uniform(0, delay * 0.25)
    logger.warning(
        "Completion API call failed (attempt %d/%d): %s — "
        "retrying in %.1fs",
        attempt + 1, _MAX_RETRIES + 1, exc, delay,
    )
    time.sleep(delay)


def _resolve_tenant_key(tenant_key: str = "") -> str:
    """Return *tenant_key* if given, otherwise fall back to ambient."""
    if tenant_key:
        return tenant_key
    try:
        from airunner_services.data.tenant import get_tenant_key

        return get_tenant_key() or ""
    except Exception:
        return ""


def invoke_with_limiter(
    model: Any,
    messages: Any,
    *,
    priority: Literal["live", "bulk"] = "live",
    tenant_key: str = "",
    max_retries: int = _MAX_RETRIES,
    **kwargs: Any,
) -> Any:
    """Call ``model.invoke(messages, **kwargs)`` with admission control.

    Acquires a distributed concurrency slot from the priority-lane
    limiter before calling the model, releases it afterward.  Retries
    transient failures (429/5xx) with exponential backoff — this
    retry logic did NOT exist on the completion path before this work.

    *priority*:
        ``"live"`` — short bounded wait, then raises ``RuntimeError``
        if no slot frees up (no clean "skip it" degrade for completions
        the way embeddings have — the caller must handle this).
        ``"bulk"`` — retries with backoff until a slot is available
        or *max_retries* is exhausted.

    Returns the model's response on success.
    """
    from airunner_services.cloud.distributed_limiter import (
        AcquiredSlot,
        acquire_slot,
        acquire_with_retry,
    )

    tk = _resolve_tenant_key(tenant_key)

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        # --- Acquire admission slot ---
        slot: AcquiredSlot | None = None
        if priority == "live":
            slot = acquire_with_retry(
                "completion", "live", tk,
                max_wait=_LIVE_WAIT_MAX_SECONDS,
                poll_interval=_LIVE_WAIT_POLL_SECONDS,
            )
        else:
            slot = acquire_slot("completion", "bulk", tk)

        if slot is None:
            if priority == "live":
                raise LiveLaneExhaustedError(
                    "Completion live lane exhausted — "
                    "no slot freed up within bounded wait"
                )
            # Bulk: no slot available, retry with backoff
            if attempt < max_retries:
                _sleep_before_retry(attempt, RuntimeError(
                    "Completion bulk lane full — waiting for slot"
                ))
                continue
            raise RuntimeError(
                "Completion bulk lane still full after "
                f"{max_retries} retries"
            )

        try:
            response = model.invoke(messages, **kwargs)
            slot.release()
            return response
        except Exception as exc:
            slot.release()
            if not _is_retryable_error(exc) or attempt >= max_retries:
                raise
            last_exc = exc
            _sleep_before_retry(attempt, exc)

    raise last_exc or RuntimeError(
        "Completion invoke failed with no captured exception",
    )


def stream_with_limiter(
    model: Any,
    messages: Any,
    *,
    priority: Literal["live", "bulk"] = "live",
    tenant_key: str = "",
    max_retries: int = _MAX_RETRIES,
    **kwargs: Any,
) -> Iterator[Any]:
    """Call ``model.stream(messages, **kwargs)`` with admission control.

    Acquires a distributed concurrency slot for the entire stream
    duration (the slot represents a concurrent request in flight,
    which streaming requests genuinely are).  Uses ``try/finally``
    so the slot is released immediately on **any** generator exit —
    normal completion, exception, or ``GeneratorExit`` (caller
    cancels / stops iterating).  No slot leaks via lease expiry.

    Retries transient failures (429/5xx) with exponential backoff —
    the entire stream is retried, not individual chunks.
    """
    from airunner_services.cloud.distributed_limiter import (
        AcquiredSlot,
        acquire_slot,
        acquire_with_retry,
    )

    tk = _resolve_tenant_key(tenant_key)

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        slot: AcquiredSlot | None = None
        if priority == "live":
            slot = acquire_with_retry(
                "completion", "live", tk,
                max_wait=_LIVE_WAIT_MAX_SECONDS,
                poll_interval=_LIVE_WAIT_POLL_SECONDS,
            )
        else:
            slot = acquire_slot("completion", "bulk", tk)

        if slot is None:
            if priority == "live":
                raise LiveLaneExhaustedError(
                    "Completion live lane exhausted — "
                    "no slot freed up within bounded wait"
                )
            if attempt < max_retries:
                _sleep_before_retry(attempt, RuntimeError(
                    "Completion bulk lane full — waiting for slot"
                ))
                continue
            raise RuntimeError(
                "Completion bulk lane still full after "
                f"{max_retries} retries"
            )

        try:
            for chunk in model.stream(messages, **kwargs):
                yield chunk
            return
        except Exception as exc:
            if not _is_retryable_error(exc) or attempt >= max_retries:
                raise
            last_exc = exc
            _sleep_before_retry(attempt, exc)
        finally:
            slot.release()

    raise last_exc or RuntimeError(
        "Completion stream failed with no captured exception",
    )
