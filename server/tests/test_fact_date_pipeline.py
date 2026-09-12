"""Unit tests for Stage B extraction and full resolve_fact_dates pipeline.

LLM calls are mocked so tests are deterministic.
"""
from __future__ import annotations

import datetime
from unittest.mock import patch

from airunner_services.fact_date_extractor import (
    _extract_dates_stage_b,
    resolve_fact_dates,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _mock_llm_returns(text: str):
    """Return a patch for _call_classification_llm."""
    return patch(
        "airunner_services.fact_date_extractor._call_classification_llm",
        return_value=text,
    )


# ---------------------------------------------------------------------------
# Stage B extraction tests
# ---------------------------------------------------------------------------


def test_extract_release_friday() -> None:
    """Stage B extracts correct date for 'release is Friday'."""
    response = (
        '{"event_date": "2026-06-19", '
        '"event_end_date": null, '
        '"event_time": null, '
        '"recurring": false}'
    )
    with _mock_llm_returns(response):
        result = _extract_dates_stage_b(
            "release is Friday",
            datetime.date(2026, 6, 15),
        )
    assert result is not None
    assert result["event_date"] == "2026-06-19"
    assert result["event_end_date"] is None
    assert result["recurring"] is False


def test_extract_therapy_every_tuesday() -> None:
    """Stage B detects recurring pattern."""
    response = (
        '{"event_date": "2026-07-28", '
        '"event_end_date": null, '
        '"event_time": null, '
        '"recurring": true}'
    )
    with _mock_llm_returns(response):
        result = _extract_dates_stage_b(
            "therapy every Tuesday",
            datetime.date(2026, 7, 26),
        )
    assert result is not None
    assert result["recurring"] is True
    assert result["event_date"] == "2026-07-28"


def test_extract_vacation_range() -> None:
    """Stage B extracts date range for vacation."""
    response = (
        '{"event_date": "2026-07-20", '
        '"event_end_date": "2026-07-27", '
        '"event_time": null, '
        '"recurring": false}'
    )
    with _mock_llm_returns(response):
        result = _extract_dates_stage_b(
            "on vacation July 20-27",
            datetime.date(2026, 7, 1),
        )
    assert result is not None
    assert result["event_date"] == "2026-07-20"
    assert result["event_end_date"] == "2026-07-27"


def test_extract_meeting_at_3pm() -> None:
    """Stage B extracts event_time for same-day event."""
    response = (
        '{"event_date": "2026-07-26", '
        '"event_end_date": null, '
        '"event_time": "15:00", '
        '"recurring": false}'
    )
    with _mock_llm_returns(response):
        result = _extract_dates_stage_b(
            "meeting at 3pm today",
            datetime.date(2026, 7, 26),
        )
    assert result is not None
    assert result["event_time"] == "15:00"
    assert result["event_date"] == "2026-07-26"


# ---------------------------------------------------------------------------
# resolve_fact_dates (full pipeline) tests
# ---------------------------------------------------------------------------


def test_resolve_hard_date_pipeline() -> None:
    """Full pipeline: Stage A hard_date → Stage B extraction."""
    with patch(
        "airunner_services.fact_date_extractor._call_classification_llm"
    ) as mock_llm:
        mock_llm.side_effect = [
            "hard_date",
            '{"event_date": "2026-06-19", '
            '"event_end_date": null, '
            '"event_time": null, '
            '"recurring": false}',
        ]
        result = resolve_fact_dates(
            "release is Friday",
            datetime.date(2026, 6, 15),
        )
    assert result is not None
    assert result["event_date"] == "2026-06-19"
    assert result["recurring"] is False
    # reference_date (June 15) < event_date (June 19) → upcoming
    assert result["temporal_status"] == "upcoming"


def test_resolve_soft_aspirational_returns_none() -> None:
    """Stage A soft_aspirational → no Stage B, returns None."""
    with _mock_llm_returns("soft_aspirational"):
        result = resolve_fact_dates(
            "wants to travel sometime this year",
            datetime.date(2026, 7, 26),
        )
    assert result is None


def test_resolve_no_date_returns_none() -> None:
    """Stage A no_date → no Stage B, returns None."""
    with _mock_llm_returns("no_date"):
        result = resolve_fact_dates(
            "user's name is Joe",
            datetime.date(2026, 7, 26),
        )
    assert result is None


def test_resolve_upcoming_event() -> None:
    """Full pipeline for an upcoming event."""
    with patch(
        "airunner_services.fact_date_extractor._call_classification_llm"
    ) as mock_llm:
        mock_llm.side_effect = [
            "hard_date",
            '{"event_date": "2026-08-15", '
            '"event_end_date": null, '
            '"event_time": null, '
            '"recurring": false}',
        ]
        result = resolve_fact_dates(
            "deadline is August 15",
            datetime.date(2026, 7, 26),
        )
    assert result is not None
    assert result["event_date"] == "2026-08-15"
    assert result["temporal_status"] == "upcoming"


def test_resolve_range_in_progress() -> None:
    """Full pipeline for an in-progress range event."""
    with patch(
        "airunner_services.fact_date_extractor._call_classification_llm"
    ) as mock_llm:
        mock_llm.side_effect = [
            "hard_date",
            '{"event_date": "2026-07-20", '
            '"event_end_date": "2026-07-27", '
            '"event_time": null, '
            '"recurring": false}',
        ]
        result = resolve_fact_dates(
            "on vacation July 20-27",
            datetime.date(2026, 7, 23),
        )
    assert result is not None
    assert result["temporal_status"] == "in_progress"
    assert result["event_end_date"] == "2026-07-27"


def test_resolve_model_failure_returns_none() -> None:
    """Empty LLM response → resolve_fact_dates returns None."""
    with _mock_llm_returns(""):
        result = resolve_fact_dates(
            "release is Friday",
            datetime.date(2026, 6, 15),
        )
    assert result is None
