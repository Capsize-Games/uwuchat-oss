"""Heuristic detection of overused generic-validation crutch phrases.

Catches the ``"it sounds like"`` / therapist-speak pattern — a
different class of bug than the exact-message-repeat check in
``quality_metrics.evaluate_conversation_coherence()``, which only
detects verbatim duplicates.

Usage::

    from airunner_services.eval.utils.crutch_detector import (
        CRUTCH_PHRASES,
        detect_crutch_phrases,
    )
    result = detect_crutch_phrases(responses, max_rate=0.15)
    assert result["passed"]
"""

from typing import Any

# Crutch phrases to scan for — mirrors the banned list in
# ``BANNED_PATTERNS_BLOCK`` (projects/uwuchat/server/prompt_rules.py)
# plus common generic-validation variants worth guarding against.
CRUTCH_PHRASES: list[str] = [
    "it sounds like",
    "sounds like you're",
    "sounds like",
    "it seems like",
    "seems like you're",
    "that sounds like",
    "that's really interesting",
    "that makes sense",
    "i hear you",
    "that's a great question",
    "that's such a",
]


def _scan_responses(
    responses: list[str],
    phrases: list[str],
) -> tuple[int, list[str]]:
    """Return (hit_count, phrases_found) for one batch of responses."""
    hits = 0
    found: list[str] = []
    for response in responses:
        lowered = response.lower()
        for phrase in phrases:
            if phrase in lowered:
                hits += 1
                found.append(phrase)
                break  # count each response at most once
    return hits, found


def _build_details(
    rate: float, max_rate: float, passed: bool,
    phrases_found: list[str],
) -> str:
    """Build a human-readable details string from the scan results."""
    parts: list[str] = []
    if not passed:
        parts.append(
            f"Crutch phrase rate {rate:.0%} exceeds"
            f" max {max_rate:.0%}",
        )
    if phrases_found:
        unique = list(dict.fromkeys(phrases_found))
        parts.append(f"Phrases found: {unique}")
    return " | ".join(parts) if parts else "OK"


def _make_result(
    total: int, hits: int, rate: float, passed: bool,
    phrases_found: list[str], details: str,
) -> dict[str, Any]:
    """Package scan results into the standard dict shape."""
    return {
        "total": total, "hits": hits, "rate": rate,
        "passed": passed, "phrases_found": phrases_found,
        "details": details,
    }


def _empty_result() -> dict[str, Any]:
    """Return a result dict for an empty response list."""
    return _make_result(
        0, 0, 0.0, True, [], "No responses to scan.",
    )


def detect_crutch_phrases(
    responses: list[str],
    phrases: list[str] | None = None,
    max_rate: float = 0.15,
) -> dict[str, Any]:
    """Scan responses for crutch phrase overuse.

    Returns a dict with ``total``, ``hits``, ``rate``, ``passed``,
    ``phrases_found``, and ``details``.  See module docstring for
    usage and ``CRUTCH_PHRASES`` for the default phrase list.
    """
    target = phrases if phrases is not None else CRUTCH_PHRASES
    total = len(responses)
    if total == 0:
        return _empty_result()
    hits, found = _scan_responses(responses, target)
    rate = hits / total
    passed = rate <= max_rate
    details = _build_details(rate, max_rate, passed, found)
    return _make_result(total, hits, rate, passed, found, details)
