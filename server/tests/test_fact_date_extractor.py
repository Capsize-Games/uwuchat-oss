"""Unit tests for fact date parsing and Stage A classification.

Tests ``_parse_stage_b_response`` and ``_classify_date_stage_a``
with mocked LLM calls.
"""
from __future__ import annotations

import datetime
from unittest.mock import patch

from airunner_services.fact_date_extractor import (
    _classify_date_stage_a,
    _parse_stage_b_response,
)


# ---------------------------------------------------------------------------
# _parse_stage_b_response tests
# ---------------------------------------------------------------------------


def test_parse_clean_json() -> None:
    """Clean JSON object parses correctly."""
    result = _parse_stage_b_response(
        '{"event_date": "2026-06-19", '
        '"event_end_date": null, '
        '"event_time": null, '
        '"recurring": false}'
    )
    assert result is not None
    assert result["event_date"] == "2026-06-19"
    assert result["event_end_date"] is None
    assert result["event_time"] is None
    assert result["recurring"] is False


def test_parse_json_with_code_fence() -> None:
    """JSON wrapped in markdown code fence parses correctly."""
    result = _parse_stage_b_response(
        '```json\n'
        '{"event_date": "2026-07-20", '
        '"event_end_date": "2026-07-27", '
        '"event_time": null, '
        '"recurring": false}\n'
        '```'
    )
    assert result is not None
    assert result["event_date"] == "2026-07-20"
    assert result["event_end_date"] == "2026-07-27"
    assert result["recurring"] is False


def test_parse_json_with_trailing_text() -> None:
    """JSON with trailing commentary — best-effort extraction."""
    result = _parse_stage_b_response(
        '{"event_date": "2026-06-19", "event_end_date": null, '
        '"event_time": null, "recurring": false} '
        'The event is a single-day deadline.'
    )
    assert result is not None
    assert result["event_date"] == "2026-06-19"


def test_parse_with_event_time() -> None:
    """JSON with event_time parses correctly."""
    result = _parse_stage_b_response(
        '{"event_date": "2026-07-26", '
        '"event_end_date": null, '
        '"event_time": "15:00", '
        '"recurring": false}'
    )
    assert result is not None
    assert result["event_time"] == "15:00"


def test_parse_with_recurring() -> None:
    """JSON with recurring=true parses correctly."""
    result = _parse_stage_b_response(
        '{"event_date": "2026-07-28", '
        '"event_end_date": null, '
        '"event_time": null, '
        '"recurring": true}'
    )
    assert result is not None
    assert result["recurring"] is True


def test_parse_invalid_json_returns_none() -> None:
    """Totally invalid string returns None."""
    result = _parse_stage_b_response("not json at all")
    assert result is None


def test_parse_missing_event_date_returns_none() -> None:
    """JSON without event_date returns None."""
    result = _parse_stage_b_response(
        '{"event_end_date": null, '
        '"event_time": null, '
        '"recurring": false}'
    )
    assert result is None


def test_parse_invalid_date_string_ignored() -> None:
    """Invalid date string is ignored, returns None if no valid date."""
    result = _parse_stage_b_response(
        '{"event_date": "not-a-date", '
        '"event_end_date": null, '
        '"event_time": null, '
        '"recurring": false}'
    )
    assert result is None


# ---------------------------------------------------------------------------
# Stage A classification tests (mocked LLM)
# ---------------------------------------------------------------------------


def _mock_llm_returns(text: str):
    """Return a patch that makes _call_classification_llm return text."""
    return patch(
        "airunner_services.fact_date_extractor._call_classification_llm",
        return_value=text,
    )


def test_classify_hard_date() -> None:
    """Stage A returns hard_date for a specific deadline."""
    with _mock_llm_returns("hard_date"):
        result = _classify_date_stage_a(
            "release is Friday",
            datetime.date(2026, 6, 15),
        )
    assert result == "hard_date"


def test_classify_no_date() -> None:
    """Stage A returns no_date for a name fact."""
    with _mock_llm_returns("no_date"):
        result = _classify_date_stage_a(
            "user's name is Joe",
            datetime.date(2026, 7, 26),
        )
    assert result == "no_date"


def test_classify_soft_aspirational() -> None:
    """Stage A returns soft_aspirational for vague future intent."""
    with _mock_llm_returns("soft_aspirational"):
        result = _classify_date_stage_a(
            "wants to travel sometime this year",
            datetime.date(2026, 7, 26),
        )
    assert result == "soft_aspirational"


def test_classify_strips_whitespace() -> None:
    """Stage A trims whitespace from model output."""
    with _mock_llm_returns("  hard_date\n"):
        result = _classify_date_stage_a(
            "release is Friday",
            datetime.date(2026, 6, 15),
        )
    assert result == "hard_date"


def test_classify_falls_back_to_first_word() -> None:
    """If model returns extra text, first word is used."""
    with _mock_llm_returns(
        "hard_date — this fact has a specific deadline"
    ):
        result = _classify_date_stage_a(
            "release is Friday",
            datetime.date(2026, 6, 15),
        )
    assert result == "hard_date"


def test_classify_unrecognized_returns_no_date() -> None:
    """Unrecognized model output defaults to no_date."""
    with _mock_llm_returns("gibberish"):
        result = _classify_date_stage_a(
            "some fact",
            datetime.date(2026, 7, 26),
        )
    assert result == "no_date"
