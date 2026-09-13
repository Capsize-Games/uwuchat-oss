"""Tests for agent-loop prompt-cache injection.

Verifies:
1. Multi-iteration tool loop places cache_control on correct message.
2. Single-iteration loop doesn't crash when nothing to mark.
3. compute_message_char_count reflects real message-list size.
4. Messages with existing cache_control are not double-tagged.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from airunner_services.llm.agent_loop_cache import (
    compute_message_char_count,
    inject_agent_loop_cache_breakpoint,
)


class TestInjectAgentLoopCacheBreakpoint:
    """Tests for inject_agent_loop_cache_breakpoint."""

    def test_empty_list(self) -> None:
        """Returns empty list unchanged."""
        result = inject_agent_loop_cache_breakpoint([])
        assert result == []

    def test_marks_last_message(self) -> None:
        """The last message gets a cache_control content block."""
        messages = [
            SystemMessage(content="system prompt"),
            HumanMessage(content="user message"),
            AIMessage(content="tool call", tool_calls=[]),
            ToolMessage(content="tool result", tool_call_id="t1"),
        ]
        result = inject_agent_loop_cache_breakpoint(messages)
        # Last message should now have cache_control.
        last_content = result[-1].content
        assert isinstance(last_content, list)
        assert any(
            isinstance(b, dict) and "cache_control" in b
            for b in last_content
        ), f"No cache_control found in {last_content}"

    def test_original_list_unmodified(self) -> None:
        """The input list is never mutated."""
        messages = [
            SystemMessage(content="system"),
            HumanMessage(content="hello"),
        ]
        original_content = messages[-1].content
        inject_agent_loop_cache_breakpoint(messages)
        # Original last message content unchanged.
        assert messages[-1].content == original_content

    def test_noop_when_already_tagged(self) -> None:
        """Returns unchanged if last message already has cache_control."""
        messages = [
            SystemMessage(content="system"),
            ToolMessage(
                content=[{
                    "type": "text",
                    "text": "result",
                    "cache_control": {"type": "ephemeral"},
                }],
                tool_call_id="t1",
            ),
        ]
        result = inject_agent_loop_cache_breakpoint(messages)
        assert result is not messages  # new list, but ...
        # content unchanged.
        assert result[-1].content == messages[-1].content

    def test_single_message(self) -> None:
        """Works with a single-message list."""
        messages = [SystemMessage(content="only message")]
        result = inject_agent_loop_cache_breakpoint(messages)
        assert isinstance(result[-1].content, list)
        assert any(
            isinstance(b, dict) and "cache_control" in b
            for b in result[-1].content
        )

    def test_first_iteration_no_cache(self) -> None:
        """Simulates round 0: System + Human only, no cache needed."""
        messages = [
            SystemMessage(content="system"),
            HumanMessage(content="user prompt"),
        ]
        # Call without cache injection (iteration 0 behavior).
        # The helper should still work if called, but the point is
        # that it doesn't crash on a small list.
        result = inject_agent_loop_cache_breakpoint(messages)
        last_content = result[-1].content
        assert isinstance(last_content, list)
        assert any(
            isinstance(b, dict) and "cache_control" in b
            for b in last_content
        )


class TestComputeMessageCharCount:
    """Tests for compute_message_char_count."""

    def test_empty_list(self) -> None:
        """Returns 0 for empty list."""
        assert compute_message_char_count([]) == 0

    def test_string_content(self) -> None:
        """Sums string content lengths."""
        messages = [
            SystemMessage(content="abc"),    # 3
            HumanMessage(content="def"),     # 3
            AIMessage(content=""),           # 0
        ]
        assert compute_message_char_count(messages) == 6

    def test_list_content(self) -> None:
        """Sums text blocks in list content."""
        messages = [
            SystemMessage(content=[
                {"type": "text", "text": "xyz"},    # 3
                {"type": "text", "text": "uv"},      # 2
            ]),
        ]
        assert compute_message_char_count(messages) == 5

    def test_mixed_content(self) -> None:
        """Handles both string and list content in same list."""
        messages = [
            SystemMessage(content="abc"),       # 3
            ToolMessage(
                content=[{"type": "text", "text": "de"}],  # 2
                tool_call_id="t1",
            ),
        ]
        assert compute_message_char_count(messages) == 5

    def test_none_content(self) -> None:
        """Messages with None content contribute 0."""
        msg = HumanMessage(content="skip")
        msg.content = None  # type: ignore[assignment]
        assert compute_message_char_count([msg]) == 0

    def test_grows_with_iterations(self) -> None:
        """The count increases as messages accumulate across rounds."""
        msgs = [
            SystemMessage(content="sys" * 100),   # 300
            HumanMessage(content="usr" * 100),     # 300
        ]
        round0 = compute_message_char_count(msgs)
        assert round0 == 600

        # Simulate adding an AI + Tool pair.
        msgs.append(AIMessage(content="ai" * 50))        # +100
        msgs.append(ToolMessage(
            content="tool" * 100, tool_call_id="t1",     # +400
        ))
        round1 = compute_message_char_count(msgs)
        assert round1 == 600 + 100 + 400
        assert round1 > round0


class TestAgentLoopCacheIntegration:
    """Integration-style tests for cache injection in loop pattern."""

    def test_multi_iteration_cache_placement(self) -> None:
        """After each tool round, the last message carries cache_control."""
        messages = [
            SystemMessage(content="system"),
            HumanMessage(content="user prompt"),
        ]

        # Round 0: first call, no cache injection.
        list(messages)
        # Simulate AIMessage + ToolMessage appended.
        messages.append(AIMessage(
            content="", tool_calls=[{"name": "t", "args": {}, "id": "1"}],
        ))
        messages.append(ToolMessage(content="result", tool_call_id="1"))

        # Round 1: inject cache on messages before call.
        round1 = inject_agent_loop_cache_breakpoint(messages)
        # The last message (ToolMessage) should have cache_control.
        last = round1[-1]
        assert isinstance(last.content, list)
        assert any(
            isinstance(b, dict) and "cache_control" in b
            for b in last.content
        )

        # Simulate second AI + Tool pair.
        messages.append(AIMessage(
            content="", tool_calls=[{"name": "t2", "args": {}, "id": "2"}],
        ))
        messages.append(ToolMessage(content="result2", tool_call_id="2"))

        # Round 2: inject again.
        round2 = inject_agent_loop_cache_breakpoint(messages)
        last2 = round2[-1]
        assert isinstance(last2.content, list)
        assert any(
            isinstance(b, dict) and "cache_control" in b
            for b in last2.content
        )

    def test_single_iteration_no_crash(self) -> None:
        """Injecting on a 2-message list doesn't crash."""
        messages = [
            SystemMessage(content="system"),
            HumanMessage(content="user"),
        ]
        result = inject_agent_loop_cache_breakpoint(messages)
        assert len(result) == 2

    def test_bound_invoke_receives_cache_messages(self) -> None:
        """Mocked invoke receives cache_control-marked messages."""
        messages = [
            SystemMessage(content="system"),
            HumanMessage(content="user"),
        ]
        bound = MagicMock()
        bound.invoke.return_value = AIMessage(
            content="DONE",
        )

        # Round 0: no cache.
        bound.invoke(messages)
        # Round 1 (would happen after tool results appended):
        messages.append(AIMessage(
            content="",
            tool_calls=[{"name": "t", "args": {}, "id": "1"}],
        ))
        messages.append(ToolMessage(content="r", tool_call_id="1"))
        call_msgs = inject_agent_loop_cache_breakpoint(messages)
        bound.invoke(call_msgs)

        # Verify the second call had cache_control on last message.
        called_msgs = bound.invoke.call_args_list[1][0][0]
        last_content = called_msgs[-1].content
        assert isinstance(last_content, list)
        assert any(
            isinstance(b, dict) and "cache_control" in b
            for b in last_content
        )
