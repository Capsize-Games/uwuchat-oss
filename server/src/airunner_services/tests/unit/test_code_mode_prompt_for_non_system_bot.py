"""Unit tests: code-mode prompt applies to ANY chatbot, not just system bots.

Regression guard for the UwUchat code-mode bug: the code tools are bound
for every chatbot in the active project when code mode is on
(``tool_filtering_mixin/_auto.py``), but the code-mode *prompt* was gated
behind ``chatbot.is_system_bot``.  A non-system-bot conversation with code
mode on therefore got the companion persona prompt plus code tools bound —
the model refused to run them ("I can't access GitHub…").

The fix: ``parts._system_bot_core_rules_part``, ``parts._style_part`` and
``identity_parts.identity_parts`` now check ``_code_mode_active`` BEFORE the
``is_system_bot`` gate, so the code-mode prompt replaces the persona for any
chatbot when the project's code-mode toggle is on.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder import (
    identity_parts as id_parts,
)
from airunner_services.llm.managers.prompt_builder import parts

_CODE_MODE_MARKER = "You are operating in CODE MODE"


def _non_system_bot_owner() -> SimpleNamespace:
    """Return an owner whose chatbot is a non-system-bot (RP persona)."""
    owner = SimpleNamespace()
    owner.chatbot = SimpleNamespace(
        is_system_bot=False,
        botname="Aria",
        allow_narrative_text=True,
        id=2,
    )
    return owner


def _system_bot_owner() -> SimpleNamespace:
    """Return an owner whose chatbot is the system bot."""
    owner = SimpleNamespace()
    owner.chatbot = SimpleNamespace(
        is_system_bot=True,
        botname="UwU",
        allow_narrative_text=False,
        id=1,
    )
    return owner


class TestCodeModePromptNonSystemBot:
    """Code-mode prompt replaces the persona for non-system-bot chatbots."""

    def test_core_rules_are_code_mode_for_non_system_bot(self) -> None:
        """With code mode ON, a non-system-bot gets the code-mode rules."""
        owner = _non_system_bot_owner()
        with patch.object(parts, "_code_mode_active", return_value=True):
            result = parts._system_bot_core_rules_part(owner)
        assert result is not None
        assert _CODE_MODE_MARKER in result

    def test_style_is_code_mode_for_non_system_bot(self) -> None:
        """With code mode ON, a non-system-bot gets code-mode style."""
        owner = _non_system_bot_owner()
        with patch.object(parts, "_code_mode_active", return_value=True):
            result = parts._style_part(owner, LLMActionType.CHAT)
        assert result is not None
        assert _CODE_MODE_MARKER in result

    def test_topic_change_is_code_mode_for_non_system_bot(self) -> None:
        """With code mode ON, the topic-change part uses code mode."""
        owner = _non_system_bot_owner()
        with patch.object(parts, "_code_mode_active", return_value=True):
            result = parts._topic_change_rule_part(owner)
        assert result is not None

    def test_identity_is_neutral_for_non_system_bot(self) -> None:
        """With code mode ON, identity is the neutral assistant line."""
        owner = _non_system_bot_owner()
        with patch.object(id_parts, "_code_mode_active", return_value=True):
            result = id_parts.identity_parts(owner, LLMActionType.CHAT)
        assert len(result) == 1
        assert "CODE MODE" in result[0]
        assert "Aria" not in result[0]


class TestCodeModePromptSystemBotRegression:
    """System-bot behavior is unchanged (still gets code mode when on)."""

    def test_core_rules_code_mode_for_system_bot(self) -> None:
        """System-bot with code mode ON still gets code-mode rules."""
        owner = _system_bot_owner()
        with patch.object(parts, "_code_mode_active", return_value=True):
            result = parts._system_bot_core_rules_part(owner)
        assert result is not None
        assert _CODE_MODE_MARKER in result


class TestCompanionModeRegression:
    """Code mode OFF keeps the companion persona for non-system bots."""

    def test_style_keeps_persona_when_code_mode_off(self) -> None:
        """Non-system-bot without code mode keeps its RP persona style."""
        owner = _non_system_bot_owner()
        with patch.object(parts, "_code_mode_active", return_value=False):
            result = parts._style_part(owner, LLMActionType.CHAT)
        assert result is not None
        assert "You are Aria" in result

    def test_core_rules_none_when_code_mode_off(self) -> None:
        """Non-system-bot without code mode has no system-bot core rules."""
        owner = _non_system_bot_owner()
        with patch.object(parts, "_code_mode_active", return_value=False):
            result = parts._system_bot_core_rules_part(owner)
        assert result is None

    def test_identity_keeps_persona_when_code_mode_off(self) -> None:
        """Non-system-bot without code mode keeps its persona identity."""
        owner = _non_system_bot_owner()
        with patch.object(id_parts, "_code_mode_active", return_value=False):
            result = id_parts.identity_parts(owner, LLMActionType.CHAT)
        joined = " ".join(result)
        assert "Aria" in joined
        assert "CODE MODE" not in joined
