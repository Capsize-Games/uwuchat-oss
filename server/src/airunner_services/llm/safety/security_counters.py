"""Per-account security event counters.

Tracks how many times each account has triggered an injection
block or SSRF guard so this signal is visible for operator review.
Does NOT automate punitive action — that is a follow-up decision.
"""

from __future__ import annotations

from collections import defaultdict
from threading import Lock

from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_lock = Lock()
_injection_blocks: dict[int, int] = defaultdict(int)
_ssrf_blocks: dict[int, int] = defaultdict(int)


def increment_injection_block(account_id: int) -> None:
    """Increment the injection-block counter for *account_id*."""
    with _lock:
        _injection_blocks[account_id] += 1
        count = _injection_blocks[account_id]
    logger.info(
        "[Security] account %s: injection block #%s",
        account_id,
        count,
    )


def increment_ssrf_block(account_id: int) -> None:
    """Increment the SSRF-block counter for *account_id*."""
    with _lock:
        _ssrf_blocks[account_id] += 1
        count = _ssrf_blocks[account_id]
    logger.info(
        "[Security] account %s: SSRF block #%s",
        account_id,
        count,
    )


def get_injection_blocks(account_id: int) -> int:
    """Return the current injection-block count for *account_id*."""
    with _lock:
        return _injection_blocks.get(account_id, 0)


def get_ssrf_blocks(account_id: int) -> int:
    """Return the current SSRF-block count for *account_id*."""
    with _lock:
        return _ssrf_blocks.get(account_id, 0)


def reset(account_id: int) -> None:
    """Clear all counters for *account_id*."""
    with _lock:
        _injection_blocks.pop(account_id, None)
        _ssrf_blocks.pop(account_id, None)


def reset_all() -> None:
    """Clear all counters (for tests)."""
    with _lock:
        _injection_blocks.clear()
        _ssrf_blocks.clear()
