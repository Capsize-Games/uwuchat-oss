"""Unit tests for _datetime_part() trust-clause behavior."""

from __future__ import annotations

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.per_turn_context \
    import _datetime_part


def test_datetime_part_includes_trust_clause_utc_fallback() -> None:
    """UTC fallback branch must include the trust framing clause."""
    class Owner:
        chatbot = None
        llm_request = None

    result = _datetime_part(Owner(), LLMActionType.CHAT)
    assert result is not None
    assert "this is accurate" in result
    assert "trust it" in result
    assert "Current date and time (UTC):" in result


def test_datetime_part_returns_none_for_non_datetime_action() -> None:
    """Non-datetime actions must return None."""
    class Owner:
        chatbot = None
        llm_request = None

    result = _datetime_part(Owner(), LLMActionType.UPDATE_MOOD)
    assert result is None


def test_datetime_part_includes_trust_clause_with_user_local_time() -> None:
    """User local time branch must include the trust framing clause."""
    class FakeRequest:
        user_local_time = "2026-07-11 09:15:00 MDT"

    class Owner:
        chatbot = None
        llm_request = FakeRequest()

    result = _datetime_part(Owner(), LLMActionType.CHAT)
    assert result is not None
    assert "User's local date and time:" in result
    assert "this is accurate" in result
    assert "trust it" in result
    assert "2026-07-11 09:15:00 MDT" in result
