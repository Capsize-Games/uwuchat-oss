"""Tests for _format_messages_for_summary and its helpers.

Validates that tool-call identity is preserved and tool results are
attributed to their originating tool name during summarization input
formatting.
"""

from __future__ import annotations


def _make_fake_message(
    msg_type: str,
    content: str = "",
    tool_calls: list | None = None,
    name: str | None = None,
    tool_call_id: str | None = None,
):
    """Build a minimal stand-in for a LangChain message."""
    msg = type("FakeMessage", (), {})()
    msg.type = msg_type
    msg.content = content
    msg.tool_calls = tool_calls
    msg.name = name
    msg.tool_call_id = tool_call_id
    return msg


class TestFormatMessagesForSummary:
    """Verify message formatting for the summarizer input."""

    # -- Plain conversation (existing behaviour) ------------------------

    def test_plain_conversation_unchanged(self) -> None:
        """A user + assistant exchange produces the same labelled text."""
        from airunner_services.llm.managers.mixins import (
            conversation_summarization as cs,
        )

        messages = [
            _make_fake_message("human", content="hello what's the weather"),
            _make_fake_message("ai", content="let me check for you"),
        ]
        result = cs._format_messages_for_summary(messages)
        assert "User: hello what's the weather" in result
        assert "Assistant: let me check for you" in result

    def test_ai_message_without_content_skipped(self) -> None:
        """An AI message with no content and no tool calls is skipped."""
        from airunner_services.llm.managers.mixins import (
            conversation_summarization as cs,
        )

        messages = [
            _make_fake_message("human", content="hi"),
            _make_fake_message("ai", content=""),
            _make_fake_message("ai", content="actual reply"),
        ]
        result = cs._format_messages_for_summary(messages)
        assert "User: hi" in result
        assert "Assistant: actual reply" in result
        assert result.count("Assistant:") == 1

    # -- Tool-call messages (the fix) -----------------------------------

    def test_ai_tool_call_without_content_is_preserved(self) -> None:
        """An AIMessage with tool_calls but empty content is NOT dropped."""
        from airunner_services.llm.managers.mixins import (
            conversation_summarization as cs,
        )

        messages = [
            _make_fake_message("human", content="what's the news"),
            _make_fake_message(
                "ai",
                content="",
                tool_calls=[
                    {
                        "name": "search_news",
                        "args": {"q": "climate"},
                        "id": "tc1",
                    },
                ],
            ),
        ]
        result = cs._format_messages_for_summary(messages)
        assert "search_news" in result, (
            "Tool-call message should not be dropped: %r" % result
        )
        assert "Assistant called tools" in result

    def test_ai_tool_call_with_content_includes_both(self) -> None:
        """AIMessage with tool_calls AND content shows both."""
        from airunner_services.llm.managers.mixins import (
            conversation_summarization as cs,
        )

        messages = [
            _make_fake_message(
                "ai",
                content="let me search",
                tool_calls=[
                    {
                        "name": "search_fastsearch",
                        "args": {"query": "test"},
                        "id": "tc2",
                    },
                ],
            ),
        ]
        result = cs._format_messages_for_summary(messages)
        assert "let me search" in result
        assert "search_fastsearch" in result

    def test_tool_result_attributed_by_name(self) -> None:
        """ToolMessage with .name shows 'Tool result (tool_name)'."""
        from airunner_services.llm.managers.mixins import (
            conversation_summarization as cs,
        )

        messages = [
            _make_fake_message(
                "tool",
                content="sunny 22C",
                name="get_weather",
                tool_call_id="tc3",
            ),
        ]
        result = cs._format_messages_for_summary(messages)
        assert "Tool result (get_weather)" in result
        assert "sunny 22C" in result

    def test_tool_result_attributed_by_cross_reference(self) -> None:
        """ToolMessage without .name resolves via preceding AIMessage."""
        from airunner_services.llm.managers.mixins import (
            conversation_summarization as cs,
        )

        messages = [
            _make_fake_message(
                "ai",
                content="",
                tool_calls=[
                    {"name": "search_news", "args": {}, "id": "tc_cross"},
                ],
            ),
            _make_fake_message(
                "tool",
                content="headline: something happened",
                name=None,
                tool_call_id="tc_cross",
            ),
        ]
        result = cs._format_messages_for_summary(messages)
        assert "Tool result (search_news)" in result, (
            "Should resolve tool name from preceding AIMessage: %r" % result
        )
        assert "headline" in result

    def test_tool_result_no_name_and_no_match(self) -> None:
        """ToolMessage with no name and no matching AIMessage shows
        generic label."""
        from airunner_services.llm.managers.mixins import (
            conversation_summarization as cs,
        )

        messages = [
            _make_fake_message(
                "tool",
                content="some data",
                name=None,
                tool_call_id="no_such_id",
            ),
        ]
        result = cs._format_messages_for_summary(messages)
        assert "Tool result: some data" in result

    def test_full_tool_roundtrip_preserves_identity(self) -> None:
        """A complete user → AI tool call → tool result sequence
        preserves all three entries with correct tool attribution."""
        from airunner_services.llm.managers.mixins import (
            conversation_summarization as cs,
        )

        messages = [
            _make_fake_message("human", content="weather in london?"),
            _make_fake_message(
                "ai",
                content="",
                tool_calls=[
                    {
                        "name": "get_weather",
                        "args": {"location": "London"},
                        "id": "tc_full",
                    },
                ],
            ),
            _make_fake_message(
                "tool",
                content="rainy 10C",
                name=None,
                tool_call_id="tc_full",
            ),
            _make_fake_message(
                "ai", content="it's rainy and 10C in London"
            ),
        ]
        result = cs._format_messages_for_summary(messages)
        assert "User: weather in london?" in result
        assert "get_weather" in result
        assert "Tool result (get_weather)" in result
        assert "rainy 10C" in result
        assert "it's rainy and 10C in London" in result


class TestResolveToolName:
    """Direct tests for _resolve_tool_name."""

    def test_returns_name_when_present(self) -> None:
        """When ToolMessage has .name, return it directly."""
        from airunner_services.llm.managers.mixins import (
            conversation_summarization as cs,
        )

        tool_msg = _make_fake_message(
            "tool", name="search_news", tool_call_id=None
        )
        result = cs._resolve_tool_name(tool_msg, [])
        assert result == "search_news"

    def test_returns_none_when_no_name_and_no_id(self) -> None:
        """No .name and no .tool_call_id → None."""
        from airunner_services.llm.managers.mixins import (
            conversation_summarization as cs,
        )

        tool_msg = _make_fake_message(
            "tool", name=None, tool_call_id=None
        )
        result = cs._resolve_tool_name(tool_msg, [])
        assert result is None

    def test_cross_references_when_name_missing(self) -> None:
        """When .name is missing, resolve via tool_call_id."""
        from airunner_services.llm.managers.mixins import (
            conversation_summarization as cs,
        )

        tool_msg = _make_fake_message(
            "tool", name=None, tool_call_id="abc123"
        )
        ai_msg = _make_fake_message(
            "ai",
            tool_calls=[{"name": "get_weather", "id": "abc123"}],
        )
        result = cs._resolve_tool_name(tool_msg, [ai_msg])
        assert result == "get_weather"
