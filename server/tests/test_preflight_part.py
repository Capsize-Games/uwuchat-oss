"""Tests for _preflight_part — deflect-note wording split by bot type.

System bots must not be told to accuse/interrogate the user when the
preflight injection scanner flags a message (which can false-positive
on ordinary requests); roleplay bots keep the original in-character
dismissal behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from airunner_services.llm.managers.prompt_builder.per_turn_context import (
    _preflight_part,
)
from airunner_services.llm.safety.preflight import (
    PreflightOutcome,
    PreflightResult,
)


def _make_owner(is_system_bot: bool, outcome: PreflightOutcome) -> MagicMock:
    chatbot = MagicMock()
    chatbot.is_system_bot = is_system_bot
    owner = MagicMock()
    owner.chatbot = chatbot
    owner._preflight_result = PreflightResult(outcome=outcome)
    return owner


def test_system_bot_deflect_is_calm_and_non_accusatory() -> None:
    """System bot deflect note must not accuse or interrogate the user."""
    owner = _make_owner(True, PreflightOutcome.IN_CHARACTER_DEFLECT)
    result = _preflight_part(owner)
    assert result is not None
    assert "just answer that plainly and helpfully" in result
    assert "manipulate or destabilise you" not in result
    assert "ask them to explain or justify their message" in result


def test_roleplay_bot_deflect_keeps_original_wording() -> None:
    """Roleplay bot deflect note is unchanged from the original text."""
    owner = _make_owner(False, PreflightOutcome.IN_CHARACTER_DEFLECT)
    result = _preflight_part(owner)
    assert result is not None
    assert "manipulate or destabilise you" in result
    assert "dismissal, amusement, or irritation" in result


def test_no_preflight_result_returns_none() -> None:
    """No preflight result at all yields no injected text."""
    owner = MagicMock()
    owner._preflight_result = None
    assert _preflight_part(owner) is None


def test_crisis_outcome_unaffected_by_bot_type() -> None:
    """CRISIS outcome text is unchanged regardless of is_system_bot."""
    owner = _make_owner(True, PreflightOutcome.CRISIS)
    result = _preflight_part(owner)
    assert result is not None
    assert "struggling emotionally" in result
