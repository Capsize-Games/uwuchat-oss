"""Unit tests for world.temporal_query relative-date parsing.

Covers the date-phrase detector and the UTC range conversion for
"yesterday", "today", weekday names, and "N days ago" phrases — the
inputs that flow into ConversationTurn.created_at filters.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from airunner_services.world.temporal_query import (
    _is_date_query,
    parse_relative_date_range,
    resolve_reference_datetime,
)

# Reference "now" in a fixed UTC instant so assertions are deterministic.
_REF = datetime(2026, 1, 15, 20, 30, tzinfo=timezone.utc)  # a Thursday


# ---------------------------------------------------------------------------
# _is_date_query
# ---------------------------------------------------------------------------


class TestIsDateQuery:
    """Tests for _is_date_query."""

    @pytest.mark.parametrize(
        "text",
        [
            "what did we talk about yesterday",
            "last night was fun",
            "remind me about today",
            "this morning summary",
            "what happened this week",
            "plans from last week",
            "talk to me about monday",
            "we met 3 days ago",
            "what did we discuss earlier today",
        ],
    )
    def test_detects_date_phrases(self, text: str) -> None:
        """Relative-date phrases are detected case-insensitively."""
        assert _is_date_query(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "what is the weather like",
            "tell me a story",
            "where should we eat",
            "who is the president",
        ],
    )
    def test_ignores_plain_queries(self, text: str) -> None:
        """Non-date queries are not flagged."""
        assert _is_date_query(text) is False


# ---------------------------------------------------------------------------
# parse_relative_date_range
# ---------------------------------------------------------------------------


class TestParseRelativeDateRange:
    """Tests for parse_relative_date_range."""

    def test_returns_none_for_plain_query(self) -> None:
        """A query with no date phrase returns None."""
        assert parse_relative_date_range("hello there", _REF) is None

    def test_yesterday(self) -> None:
        """'yesterday' spans [local midnight - 1d, local midnight)."""
        start, end = parse_relative_date_range("yesterday", _REF)
        local_midnight = _REF.replace(hour=0, minute=0, second=0, microsecond=0)
        assert start == (local_midnight - timedelta(days=1)).replace(tzinfo=None)
        assert end == local_midnight.replace(tzinfo=None)

    def test_last_night(self) -> None:
        """'last night' is equivalent to 'yesterday'."""
        start, end = parse_relative_date_range("last night", _REF)
        local_midnight = _REF.replace(hour=0, minute=0, second=0, microsecond=0)
        assert start == (local_midnight - timedelta(days=1)).replace(tzinfo=None)

    def test_today(self) -> None:
        """'today' spans the full local day."""
        start, end = parse_relative_date_range("today", _REF)
        local_midnight = _REF.replace(hour=0, minute=0, second=0, microsecond=0)
        assert start == local_midnight.replace(tzinfo=None)
        assert end == (local_midnight + timedelta(days=1)).replace(tzinfo=None)

    def test_this_morning(self) -> None:
        """'this morning' is treated as the current local day."""
        start, _ = parse_relative_date_range("this morning", _REF)
        local_midnight = _REF.replace(hour=0, minute=0, second=0, microsecond=0)
        assert start == local_midnight.replace(tzinfo=None)

    def test_this_week_starts_on_monday(self) -> None:
        """'this week' starts at the most recent local Monday."""
        start, end = parse_relative_date_range("this week", _REF)
        local_midnight = _REF.replace(hour=0, minute=0, second=0, microsecond=0)
        monday = local_midnight - timedelta(days=local_midnight.weekday())
        assert start == monday.replace(tzinfo=None)
        assert end == (local_midnight + timedelta(days=1)).replace(tzinfo=None)

    def test_last_week(self) -> None:
        """'last week' spans the previous Monday-to-Monday window."""
        start, end = parse_relative_date_range("last week", _REF)
        local_midnight = _REF.replace(hour=0, minute=0, second=0, microsecond=0)
        this_monday = local_midnight - timedelta(days=local_midnight.weekday())
        assert start == (this_monday - timedelta(days=7)).replace(tzinfo=None)
        assert end == this_monday.replace(tzinfo=None)

    def test_weekday_name(self) -> None:
        """A bare weekday refers to the most recent past occurrence."""
        start, end = parse_relative_date_range("monday", _REF)
        local_midnight = _REF.replace(hour=0, minute=0, second=0, microsecond=0)
        # _REF is Thursday (weekday 3); most recent Monday is 3 days back.
        monday = local_midnight - timedelta(days=3)
        assert start == monday.replace(tzinfo=None)
        assert end == (monday + timedelta(days=1)).replace(tzinfo=None)

    def test_today_is_skipped_as_weekday_anchor(self) -> None:
        """The weekday branch never fires for 'today'."""
        # The weekday branch is guarded by the earlier 'today' branch.
        result = parse_relative_date_range("today", _REF)
        assert result is not None
        assert result[1] - result[0] == timedelta(days=1)

    def test_n_days_ago(self) -> None:
        """'N days ago' anchors on local midnight N days back."""
        start, end = parse_relative_date_range("3 days ago", _REF)
        local_midnight = _REF.replace(hour=0, minute=0, second=0, microsecond=0)
        expected = local_midnight - timedelta(days=3)
        assert start == expected.replace(tzinfo=None)
        assert end == (expected + timedelta(days=1)).replace(tzinfo=None)

    def test_timezone_conversion_to_naive_utc(self) -> None:
        """A non-UTC reference timezone is converted to naive UTC."""
        ny = timezone(timedelta(hours=-5))
        ref = datetime(2026, 1, 15, 23, 30, tzinfo=ny)  # 04:30 UTC Jan 16
        start, end = parse_relative_date_range("today", ref)
        # Local midnight Jan 15 in NY == 05:00 UTC Jan 15.
        expected_start = datetime(2026, 1, 15, 5, 0, 0)
        assert start == expected_start
        assert end == expected_start + timedelta(days=1)


# ---------------------------------------------------------------------------
# resolve_reference_datetime
# ---------------------------------------------------------------------------


class TestResolveReferenceDatetime:
    """Tests for resolve_reference_datetime."""

    def test_utc_when_no_location(self) -> None:
        """No location timezone resolves to UTC."""
        chatbot = SimpleNamespace(location=None)
        result = resolve_reference_datetime(chatbot)
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)

    def test_utc_when_location_has_no_timezone(self) -> None:
        """A location without a timezone resolves to UTC."""
        chatbot = SimpleNamespace(location={"city": "Tokyo"})
        result = resolve_reference_datetime(chatbot)
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)

    def test_location_timezone_is_used(self) -> None:
        """A location timezone is honored."""
        from zoneinfo import ZoneInfo

        chatbot = SimpleNamespace(location={"timezone": "America/New_York"})
        result = resolve_reference_datetime(chatbot)
        assert result.tzinfo == ZoneInfo("America/New_York")

    def test_missing_location_attribute(self) -> None:
        """A chatbot without a location attribute resolves to UTC."""
        chatbot = object()
        result = resolve_reference_datetime(chatbot)
        assert result.tzinfo is not None
        assert result.utcoffset() == timedelta(0)
