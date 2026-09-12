"""Shared content-injection scanner for tool results.

Used by scrape_website, read_url, search_web, search_news,
search_fastsearch, search_fastsearch_news, and get_topic_brief
to detect prompt-injection text in fetched/returned content before
it reaches the model's context.
"""

from __future__ import annotations

import re
from typing import Optional

from airunner_services.llm.safety.constants import INJECTION_PATTERNS
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

_PLACEHOLDER = "[content removed: suspicious embedded instructions]"

_HEAD_WINDOW = 5000
_TAIL_WINDOW = 5000


def _scan_window(
    window_text: str,
    content: str,
    base_offset: int,
    source_label: str,
) -> tuple[str, bool]:
    """Scan one window of text for injection patterns.

    When *base_offset* is non-zero, *window_text* is a suffix of
    *content* starting at *base_offset*.  Match spans from the
    window are translated back to absolute positions in *content*
    before splicing.

    Returns ``(content, was_flagged)`` where *content* has been
    modified in-place if a pattern matched.
    """
    for pattern in INJECTION_PATTERNS:
        match = re.search(pattern, window_text, re.IGNORECASE)
        if not match:
            continue
        logger.warning(
            "[Security] Injection pattern '%s' flagged in content "
            "(%s)",
            pattern,
            source_label,
        )
        start = base_offset + match.start()
        end = base_offset + match.end()
        return content[:start] + _PLACEHOLDER + content[end:], True
    return content, False


def scan_content_for_injection(
    content: str,
    source_label: str = "",
) -> tuple[str, bool]:
    """Scan *content* for prompt-injection patterns.

    Scans the head and tail windows independently so that match
    offsets from the tail window are correctly translated back to
    absolute positions in *content*.

    Returns ``(cleaned_content, was_flagged)``.  When a pattern
    matches, the suspicious segment is replaced with a neutral
    placeholder so the model still sees a usable result.

    Args:
        content: The text to scan (tool result, scraped page, etc.).
        source_label: Human-readable identifier for logging
            (tool name, hostname — never raw content).

    Returns:
        Tuple of ``(cleaned_content, was_flagged)``.
    """
    if not content:
        return content, False

    # Head window (positions 0 .. _HEAD_WINDOW).
    head = content[:_HEAD_WINDOW]
    result, flagged = _scan_window(head, content, 0, source_label)
    if flagged:
        return result, True

    # Tail window — only scan if content is long enough and
    # the tail does not overlap the head.
    content_len = len(content)
    if content_len > _HEAD_WINDOW:
        tail_start = max(_HEAD_WINDOW, content_len - _TAIL_WINDOW)
        tail = content[tail_start:]
        result, flagged = _scan_window(
            tail, content, tail_start, source_label,
        )
        if flagged:
            return result, True

    return content, False


def scan_content_for_injection_stripped(
    content: str,
    source_label: str = "",
) -> str:
    """Convenience wrapper that returns only the cleaned string."""
    cleaned, _ = scan_content_for_injection(content, source_label)
    return cleaned


def scan_and_log_injection(
    content: str,
    source_label: str = "",
    account_id: Optional[int] = None,
) -> tuple[str, bool]:
    """Scan and optionally increment a per-account security counter.

    Args:
        content: Text to scan.
        source_label: Tool name / host for logging.
        account_id: If set, increment the per-account injection
            counter on detection.

    Returns:
        ``(cleaned_content, was_flagged)``.
    """
    cleaned, flagged = scan_content_for_injection(content, source_label)
    if flagged and account_id is not None:
        from airunner_services.llm.safety.security_counters import (
            increment_injection_block,
        )
        increment_injection_block(account_id)
    return cleaned, flagged
