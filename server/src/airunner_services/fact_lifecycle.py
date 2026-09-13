"""Deterministic temporal-status transitions for KnowledgeFact rows.

Status transitions from ``upcoming`` / ``in_progress`` → ``resolved``
are pure date arithmetic — never an LLM call.  The only caller
compares ``event_date`` / ``event_end_date`` against a reference date
(default: today in UTC).

See ``plans/uwuchat-temporal-fact-lifecycle-and-rag-indexing-fix.md``
for the design rationale.
"""
from __future__ import annotations

import datetime
from typing import Optional


def compute_temporal_status(
    event_date: Optional[datetime.date],
    event_end_date: Optional[datetime.date],
    recurring: bool,
    reference_date: Optional[datetime.date] = None,
) -> str:
    """Return the correct ``temporal_status`` for a knowledge fact.

    Args:
        event_date: Resolved absolute start date (or ``None``).
        event_end_date: Resolved absolute end date for range events
            (or ``None``).
        recurring: ``True`` when the fact describes a repeating
            pattern (e.g. "therapy every Tuesday").  Recurring facts
            are never automatically marked ``resolved``.
        reference_date: Date to compare against (default: today in
            UTC).  Override in tests so they are not time-sensitive.

    Returns:
        One of ``"durable"``, ``"upcoming"``, ``"in_progress"``,
        or ``"resolved"``.

    Raises:
        ValueError: If *event_end_date* is set but *event_date* is
            ``None`` (a range requires a start date).
    """
    if event_date is None:
        return "durable"

    if event_end_date is not None and event_end_date < event_date:
        raise ValueError(
            f"event_end_date ({event_end_date}) is before "
            f"event_date ({event_date})"
        )

    if reference_date is None:
        reference_date = datetime.date.today()

    # Range event: in_progress between start and end (inclusive).
    if event_end_date is not None:
        if reference_date < event_date:
            return "upcoming"
        if event_date <= reference_date <= event_end_date:
            return "in_progress"
        # reference_date > event_end_date
        return "durable" if recurring else "resolved"

    # Single-date event.
    if reference_date < event_date:
        return "upcoming"
    # reference_date >= event_date
    return "durable" if recurring else "resolved"
