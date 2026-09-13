"""Unit tests for ``airunner_services.fact_lifecycle``.

Covers the Part 1 acceptance criteria plus edge cases.
"""
from __future__ import annotations

import datetime

import pytest

from airunner_services.fact_lifecycle import compute_temporal_status


# ---------------------------------------------------------------------------
# Acceptance criteria from the plan
# ---------------------------------------------------------------------------


def test_past_event_date_resolves_when_not_recurring() -> None:
    """A fact with event_date in the past, recurring=False, transitions
    to resolved when the status-check function runs."""
    status = compute_temporal_status(
        event_date=datetime.date(2026, 1, 15),
        event_end_date=None,
        recurring=False,
        reference_date=datetime.date(2026, 7, 26),
    )
    assert status == "resolved"


def test_recurring_fact_does_not_resolve_after_event_date_passes() -> None:
    """A fact with recurring=True does NOT transition to resolved after
    its event_date passes."""
    status = compute_temporal_status(
        event_date=datetime.date(2026, 1, 15),
        event_end_date=None,
        recurring=True,
        reference_date=datetime.date(2026, 7, 26),
    )
    assert status == "durable"


def test_range_fact_in_progress_between_dates() -> None:
    """A range fact is in_progress between event_date and
    event_end_date."""
    status = compute_temporal_status(
        event_date=datetime.date(2026, 7, 20),
        event_end_date=datetime.date(2026, 7, 27),
        recurring=False,
        reference_date=datetime.date(2026, 7, 23),
    )
    assert status == "in_progress"


def test_range_fact_resolved_after_end_date() -> None:
    """A range fact is resolved only after event_end_date passes."""
    status = compute_temporal_status(
        event_date=datetime.date(2026, 7, 20),
        event_end_date=datetime.date(2026, 7, 27),
        recurring=False,
        reference_date=datetime.date(2026, 7, 30),
    )
    assert status == "resolved"


def test_range_fact_upcoming_before_start() -> None:
    """A range fact is upcoming before event_date."""
    status = compute_temporal_status(
        event_date=datetime.date(2026, 8, 1),
        event_end_date=datetime.date(2026, 8, 7),
        recurring=False,
        reference_date=datetime.date(2026, 7, 26),
    )
    assert status == "upcoming"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_no_event_date_is_durable() -> None:
    """A fact with no event_date is always durable."""
    status = compute_temporal_status(
        event_date=None,
        event_end_date=None,
        recurring=False,
        reference_date=datetime.date(2026, 7, 26),
    )
    assert status == "durable"


def test_no_event_date_is_durable_even_if_recurring() -> None:
    """A fact with no event_date is always durable regardless of
    recurring flag."""
    status = compute_temporal_status(
        event_date=None,
        event_end_date=None,
        recurring=True,
        reference_date=datetime.date(2026, 7, 26),
    )
    assert status == "durable"


def test_upcoming_single_date_fact() -> None:
    """A single-date fact in the future is upcoming."""
    status = compute_temporal_status(
        event_date=datetime.date(2026, 8, 15),
        event_end_date=None,
        recurring=False,
        reference_date=datetime.date(2026, 7, 26),
    )
    assert status == "upcoming"


def test_single_date_fact_on_reference_date_is_resolved() -> None:
    """A single-date fact on the reference date is resolved
    (the day-of has arrived)."""
    status = compute_temporal_status(
        event_date=datetime.date(2026, 7, 26),
        event_end_date=None,
        recurring=False,
        reference_date=datetime.date(2026, 7, 26),
    )
    assert status == "resolved"


def test_range_fact_on_start_date_is_in_progress() -> None:
    """A range fact whose event_date equals reference_date is
    in_progress."""
    status = compute_temporal_status(
        event_date=datetime.date(2026, 7, 26),
        event_end_date=datetime.date(2026, 7, 30),
        recurring=False,
        reference_date=datetime.date(2026, 7, 26),
    )
    assert status == "in_progress"


def test_range_fact_on_end_date_is_in_progress() -> None:
    """A range fact whose event_end_date equals reference_date is
    in_progress (the last day is still in progress)."""
    status = compute_temporal_status(
        event_date=datetime.date(2026, 7, 20),
        event_end_date=datetime.date(2026, 7, 26),
        recurring=False,
        reference_date=datetime.date(2026, 7, 26),
    )
    assert status == "in_progress"


def test_recurring_range_fact_does_not_resolve() -> None:
    """A recurring range fact stays durable even after end_date
    passes."""
    status = compute_temporal_status(
        event_date=datetime.date(2026, 1, 1),
        event_end_date=datetime.date(2026, 1, 7),
        recurring=True,
        reference_date=datetime.date(2026, 7, 26),
    )
    assert status == "durable"


def test_end_date_before_start_raises() -> None:
    """A range with event_end_date < event_date raises ValueError."""
    with pytest.raises(ValueError, match="event_end_date"):
        compute_temporal_status(
            event_date=datetime.date(2026, 7, 30),
            event_end_date=datetime.date(2026, 7, 20),
            recurring=False,
            reference_date=datetime.date(2026, 7, 26),
        )
