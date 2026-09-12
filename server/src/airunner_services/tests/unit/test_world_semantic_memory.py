"""Unit tests for world.semantic_memory fact extraction."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from airunner_services.world.semantic_memory import (
    SemanticMemoryExtractor,
    _build_message_text,
    _parse_facts,
)


class TestBuildMessageText:
    """Tests for _build_message_text."""

    def test_formats_user_assistant_pairs(self) -> None:
        """Only user/assistant roles render as labeled lines."""
        messages = [
            {"role": "user", "content": "I am a nurse"},
            {"role": "assistant", "content": "Nice to meet you"},
            {"role": "system", "content": "ignored"},
            "not a dict",
        ]
        text = _build_message_text(messages)
        assert "USER: I am a nurse" in text
        assert "ASSISTANT: Nice to meet you" in text
        assert "ignored" not in text

    def test_truncates_long_content(self) -> None:
        """Content is truncated to 300 characters."""
        messages = [{"role": "user", "content": "x" * 500}]
        text = _build_message_text(messages)
        assert len(text) < 400


class TestParseFacts:
    """Tests for _parse_facts."""

    def test_extracts_string_facts(self) -> None:
        """String facts are extracted from the JSON array."""
        raw = '["fact one", "fact two", 42]'
        assert _parse_facts(raw) == ["fact one", "fact two"]

    def test_invalid_returns_empty(self) -> None:
        """Unparseable output yields an empty list."""
        assert _parse_facts("nope") == []


class TestSemanticMemoryExtractor:
    """Tests for SemanticMemoryExtractor."""

    def test_extract_stores_facts(self) -> None:
        """Extracted facts are stored for the chatbot."""
        messages = [
            {"role": "user", "content": "I work nights in Chicago"},
            {"role": "assistant", "content": "Got it"},
        ]
        extractor = SemanticMemoryExtractor(MagicMock())
        raw = '["User is a night nurse in Chicago"]'
        with (
            patch.object(extractor, "_load_messages", return_value=messages),
            patch.object(extractor, "_call_llm", return_value=raw),
            patch("airunner_services.world.semantic_memory._store_fact") as mock_store,
        ):
            extractor.extract(session_id=1, chatbot_id=7)
        mock_store.assert_called_once_with(7, "User is a night nurse in Chicago")

    def test_no_messages_noop(self) -> None:
        """No messages means no LLM call."""
        extractor = SemanticMemoryExtractor(MagicMock())
        with (
            patch.object(extractor, "_load_messages", return_value=[]),
            patch.object(extractor, "_call_llm") as mock_llm,
            patch("airunner_services.world.semantic_memory._store_fact") as mock_store,
        ):
            extractor.extract(session_id=1, chatbot_id=7)
        mock_llm.assert_not_called()
        mock_store.assert_not_called()

    def test_empty_text_noop(self) -> None:
        """A message list with no user/assistant text is skipped."""
        extractor = SemanticMemoryExtractor(MagicMock())
        with (
            patch.object(
                extractor,
                "_load_messages",
                return_value=[{"role": "system", "content": "x"}],
            ),
            patch.object(extractor, "_call_llm") as mock_llm,
            patch("airunner_services.world.semantic_memory._store_fact") as mock_store,
        ):
            extractor.extract(session_id=1, chatbot_id=7)
        mock_llm.assert_not_called()
        mock_store.assert_not_called()

    def test_load_messages_from_conversations(self) -> None:
        """Messages are pulled from the session's conversations."""
        extractor = SemanticMemoryExtractor(MagicMock())
        conv = SimpleNamespace(value=[{"role": "user", "content": "hi"}])
        with patch(
            "airunner_services.database.models.conversation.Conversation"
        ) as mock_model:
            mock_model.objects.query.return_value.filter.return_value.all.return_value = [
                conv
            ]
            assert extractor._load_messages(1) == [{"role": "user", "content": "hi"}]

    def test_load_messages_failure_empty(self) -> None:
        """A load failure degrades to an empty list."""
        extractor = SemanticMemoryExtractor(MagicMock())
        with patch(
            "airunner_services.database.models.conversation.Conversation"
        ) as mock_model:
            mock_model.objects.query.side_effect = RuntimeError("boom")
            assert extractor._load_messages(1) == []
