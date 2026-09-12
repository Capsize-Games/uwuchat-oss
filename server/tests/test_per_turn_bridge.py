"""Tests for per_turn_bridge — session-bridge wrapper text by bot type,
and relevance-gating of stale bridged content for the system bot."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.per_turn_bridge import (
    _shares_vocabulary,
    bridge_part,
)


def _make_owner(is_system_bot: bool) -> MagicMock:
    """Build a minimal mock owner with a chatbot that bridges into."""
    chatbot = MagicMock()
    chatbot.id = 1
    chatbot.name = "TestBot"
    chatbot.is_system_bot = is_system_bot
    chatbot.world_state = {}
    chatbot.voice_samples = []
    owner = MagicMock()
    owner.chatbot = chatbot
    owner._workflow_manager = None
    owner._conversation_id = None
    return owner


def _mock_append_unrelated_tail(parts: list, *_args, **_kwargs) -> None:
    """Stub: add prior-tail content unrelated to a quadratic-formula ask."""
    parts.append("User: I was talking about religion last time.")


def _mock_append_related_tail(parts: list, *_args, **_kwargs) -> None:
    """Stub: add prior-tail content that shares vocabulary with the
    quadratic-formula test message."""
    parts.append("User: Can you help me study for my quadratic exam?")


def _mock_append_unrelated_semantic(parts: list, *_args, **_kwargs) -> None:
    """Stub: add semantic content unrelated to a quadratic-formula ask."""
    parts.append("Bot: Religion is a complex topic.")


def _mock_append_related_semantic(parts: list, *_args, **_kwargs) -> None:
    """Stub: add semantic content that shares vocabulary with the
    quadratic-formula test message."""
    parts.append("Bot: The quadratic formula is useful for exams.")


def _patch_bridge(
    session_id: object = 1,
    user_message: str = "What's the quadratic formula?",
    tail_side_effect=None,
    semantic_side_effect=None,
):
    return (
        patch(
            "airunner_services.llm.managers.prompt_builder"
            ".per_turn_bridge_retrieval.get_current_session_id",
            return_value=session_id,
        ),
        patch(
            "airunner_services.llm.managers.prompt_builder"
            ".per_turn_bridge_retrieval.get_latest_user_message",
            return_value=user_message,
        ),
        patch(
            "airunner_services.llm.managers.prompt_builder"
            ".per_turn_bridge_retrieval.append_prior_tail",
            side_effect=tail_side_effect,
        ),
        patch(
            "airunner_services.llm.managers.prompt_builder"
            ".per_turn_bridge_semantic.append_semantic_context",
            side_effect=semantic_side_effect,
        ),
    )


def test_system_bot_prior_tail_shown_when_relevant() -> None:
    """System bot sees the prior-tail block, with its header, when the
    tail content shares vocabulary with the current message."""
    owner = _make_owner(is_system_bot=True)
    patches = _patch_bridge(tail_side_effect=_mock_append_related_tail)
    with patches[0], patches[1], patches[2], patches[3]:
        result = bridge_part(owner, LLMActionType.CHAT)
    assert result is not None
    assert "closed history, not an open task" in result
    assert "quadratic exam" in result


def test_system_bot_prior_tail_suppressed_when_irrelevant() -> None:
    """System bot never sees prior-tail content that shares no
    vocabulary with the current message — it is dropped entirely
    rather than shown with a "please ignore this" instruction."""
    owner = _make_owner(is_system_bot=True)
    patches = _patch_bridge(tail_side_effect=_mock_append_unrelated_tail)
    with patches[0], patches[1], patches[2], patches[3]:
        result = bridge_part(owner, LLMActionType.CHAT)
    assert result is None
    # even if some other block existed, the stale text must not leak in
    assert result is None or "religion" not in result


def test_roleplay_bot_prior_tail_always_shown() -> None:
    """Roleplay bot keeps today's behavior: tail content is shown
    regardless of relevance, with the original wrapper text."""
    owner = _make_owner(is_system_bot=False)
    patches = _patch_bridge(
        user_message="Let's continue.",
        tail_side_effect=_mock_append_unrelated_tail,
    )
    with patches[0], patches[1], patches[2], patches[3]:
        result = bridge_part(owner, LLMActionType.CHAT)
    assert result is not None
    assert "Use this as silent context only" in result
    assert "religion" in result


def test_system_bot_semantic_shown_when_relevant() -> None:
    """System bot sees the semantic block when it shares vocabulary
    with the current message."""
    owner = _make_owner(is_system_bot=True)
    patches = _patch_bridge(semantic_side_effect=_mock_append_related_semantic)
    with patches[0], patches[1], patches[2], patches[3]:
        result = bridge_part(owner, LLMActionType.CHAT)
    assert result is not None
    assert "closed history, not an open task" in result
    assert "quadratic formula is useful" in result


def test_system_bot_semantic_suppressed_when_irrelevant() -> None:
    """System bot never sees semantic content unrelated to the current
    message — it is dropped entirely."""
    owner = _make_owner(is_system_bot=True)
    patches = _patch_bridge(
        semantic_side_effect=_mock_append_unrelated_semantic
    )
    with patches[0], patches[1], patches[2], patches[3]:
        result = bridge_part(owner, LLMActionType.CHAT)
    assert result is None
    assert result is None or "Religion is a complex topic" not in result


def test_roleplay_bot_semantic_always_shown() -> None:
    """Roleplay bot keeps today's behavior for semantic content too."""
    owner = _make_owner(is_system_bot=False)
    patches = _patch_bridge(
        user_message="Let's continue.",
        semantic_side_effect=_mock_append_unrelated_semantic,
    )
    with patches[0], patches[1], patches[2], patches[3]:
        result = bridge_part(owner, LLMActionType.CHAT)
    assert result is not None
    assert "React to the current message, not to this" in result
    assert "Religion is a complex topic" in result


def test_default_no_is_system_bot_falls_back_to_roleplay() -> None:
    """Chatbot without is_system_bot attribute falls back to roleplay
    behavior — no relevance gating applied."""
    chatbot = MagicMock()
    chatbot.id = 1
    chatbot.name = "TestBot"
    chatbot.world_state = {}
    chatbot.voice_samples = []
    # Explicitly delete is_system_bot to test default-False fallback.
    del chatbot.is_system_bot
    owner = MagicMock()
    owner.chatbot = chatbot
    owner._workflow_manager = None
    owner._conversation_id = None
    patches = _patch_bridge(
        user_message="Hello.",
        tail_side_effect=_mock_append_unrelated_tail,
    )
    with patches[0], patches[1], patches[2], patches[3]:
        result = bridge_part(owner, LLMActionType.CHAT)
    assert result is not None
    assert "Use this as silent context only" in result
    assert "closed history, not an open task" not in result


def test_chatbot_is_none_returns_none() -> None:
    """bridge_part returns None when owner has no chatbot."""
    owner = MagicMock()
    owner.chatbot = None
    result = bridge_part(owner, LLMActionType.CHAT)
    assert result is None


def test_shares_vocabulary_true_on_overlap() -> None:
    """_shares_vocabulary is True when a content word overlaps."""
    assert _shares_vocabulary(
        "What's the quadratic formula?",
        "Can you help me study for my quadratic exam?",
    )


def test_shares_vocabulary_false_without_overlap() -> None:
    """_shares_vocabulary is False when no content word overlaps."""
    assert not _shares_vocabulary(
        "What's the quadratic formula?",
        "I was talking about religion last time.",
    )


def test_shares_vocabulary_true_when_user_message_empty() -> None:
    """An empty user message never triggers suppression (fail open)."""
    assert _shares_vocabulary("", "anything at all")
