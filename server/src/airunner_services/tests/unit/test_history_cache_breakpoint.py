"""Tests for conversation history cache_control breakpoint.

Verifies that:
1. The Claude path gets a history cache_control marker.
2. The non-Claude path (_build_standard_prompt) is unaffected.
3. Total cache_control blocks never exceed Anthropic's limit of 4.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from airunner_services.conf.model_settings import CLAUDE_HAIKU_MODEL


def _make_tool(name: str) -> MagicMock:
    """Return a MagicMock tool with a .name attribute."""
    t = MagicMock()
    t.name = name
    return t


class TestHistoryCacheBreakpoint:
    """Tests that conversation history receives a cache_control marker."""

    @staticmethod
    def _make_claude_owner():
        """Return a mock for the Claude segmented path."""
        from airunner_services.llm.managers.prompt_builder.prompt_segments import (
            PromptSegments,
        )
        segments = PromptSegments(
            segment_a=["IDENTITY: test"],
            segment_b=[],
            segment_c=["style block"],
        )
        owner = MagicMock()
        chat_model = MagicMock()
        chat_model.is_vision_model = False
        chat_model.model = CLAUDE_HAIKU_MODEL
        owner._chat_model = chat_model
        owner._owner = owner
        owner._prompt_segments = segments
        owner._tools = [_make_tool("search_tools")]
        owner.logger = MagicMock()
        owner._per_turn_context = ""
        owner._gather_knowledge_context = MagicMock(return_value="")
        owner._gather_conversation_context = MagicMock(return_value="")
        owner._merge_consecutive_humans = lambda msgs: msgs
        owner._inject_context_into_human_turn = lambda msgs, *a: msgs
        owner._get_post_tool_instructions_helper = MagicMock(
            return_value=MagicMock(
                get_post_tool_instruction_text=MagicMock(
                    return_value="",
                ),
            )
        )
        from airunner_services.llm.managers.mixins.node_prompt_builder_mixin import (
            NodePromptBuilderMixin,
        )
        owner._build_claude_prompt = (
            NodePromptBuilderMixin._build_claude_prompt.__get__(
                owner, NodePromptBuilderMixin
            )
        )
        owner._log_cache_prefix_segments = (
            NodePromptBuilderMixin._log_cache_prefix_segments.__get__(
                owner, NodePromptBuilderMixin
            )
        )
        owner._build_segmented_system_msg = (
            NodePromptBuilderMixin._build_segmented_system_msg
        )
        owner._inject_history_cache_control = (
            NodePromptBuilderMixin._inject_history_cache_control.__get__(
                owner, NodePromptBuilderMixin
            )
        )
        owner.chatbot = MagicMock(is_system_bot=False)
        return owner

    def test_history_gets_cache_control(self) -> None:
        """The last pre-turn message gets a cache_control marker."""
        owner = self._make_claude_owner()
        messages = [
            HumanMessage(content="previous turn question"),
            AIMessage(content="previous turn answer"),
            HumanMessage(content="current turn question"),
        ]
        from airunner_services.llm.managers.mixins.node_prompt_builder_mixin import (
            NodePromptBuilderMixin,
        )
        result = NodePromptBuilderMixin.build_prompt(owner, messages)
        msg_list = result

        # The AIMessage (pre-turn) should have cache_control.
        cc_blocks = 0
        for msg in msg_list:
            content = getattr(msg, "content", None)
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and "cache_control" in block
                    ):
                        cc_blocks += 1
        # System segments (2) + history (1) = 3 minimum
        assert cc_blocks >= 3, (
            f"Expected >=3 cache_control blocks, got {cc_blocks}"
        )

    def test_no_pre_turn_no_history_breakpoint(self) -> None:
        """When only one HumanMessage exists, no history breakpoint."""
        owner = self._make_claude_owner()
        messages = [HumanMessage(content="only turn")]
        from airunner_services.llm.managers.mixins.node_prompt_builder_mixin import (
            NodePromptBuilderMixin,
        )
        result = NodePromptBuilderMixin.build_prompt(owner, messages)
        msg_list = result

        history_cc_count = 0
        for msg in msg_list:
            if isinstance(msg, SystemMessage):
                continue
            content = getattr(msg, "content", None)
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and "cache_control" in block
                    ):
                        history_cc_count += 1
        assert history_cc_count == 0, (
            f"Expected 0 history cache_control, got {history_cc_count}"
        )

    def test_standard_path_unaffected(self) -> None:
        """The non-Claude path does NOT add a history cache_control."""
        owner = self._make_claude_owner()
        owner._is_claude_model = MagicMock(return_value=False)
        owner.escape_system_prompt = MagicMock(
            return_value="SYSTEM_PROMPT"
        )
        owner.add_tool_instructions = MagicMock(
            return_value="SYSTEM_PROMPT"
        )
        owner._log_cache_prefix_hash = MagicMock()
        owner._last_exchange_block = MagicMock(return_value="")

        called = []
        owner._inject_history_cache_control = lambda msgs: (
            called.append(True) or msgs
        )

        from airunner_services.llm.managers.mixins.node_prompt_builder_mixin import (
            NodePromptBuilderMixin,
        )
        NodePromptBuilderMixin.build_prompt(
            owner,
            [HumanMessage(content="t1"),
             AIMessage(content="a1"),
             HumanMessage(content="t2")],
        )
        assert not called, (
            "Standard path must not call _inject_history_cache_control"
        )

    def test_cache_control_count_within_limit(self) -> None:
        """Total cache_control blocks ≤ 4 (Anthropic limit)."""
        owner = self._make_claude_owner()
        messages = [
            HumanMessage(content="t1"),
            AIMessage(content="a1"),
            HumanMessage(content="t2"),
        ]
        from airunner_services.llm.managers.mixins.node_prompt_builder_mixin import (
            NodePromptBuilderMixin,
        )
        result = NodePromptBuilderMixin.build_prompt(owner, messages)
        msg_list = result

        total_cc = 0
        for msg in msg_list:
            content = getattr(msg, "content", None)
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and "cache_control" in block
                    ):
                        total_cc += 1
        assert total_cc <= 4, (
            f"Total cache_control blocks {total_cc} exceeds limit of 4"
        )

    def test_cache_control_count_with_segment_b(self) -> None:
        """With segment B present + history, total ≤ 4."""
        from airunner_services.llm.managers.prompt_builder.prompt_segments import (
            PromptSegments,
        )
        owner = self._make_claude_owner()
        seg = PromptSegments(
            segment_a=["IDENTITY: test"],
            segment_b=["HARD RULES"],
            segment_c=["style block"],
        )
        owner._prompt_segments = seg
        messages = [
            HumanMessage(content="t1"),
            AIMessage(content="a1"),
            HumanMessage(content="t2"),
        ]
        from airunner_services.llm.managers.mixins.node_prompt_builder_mixin import (
            NodePromptBuilderMixin,
        )
        result = NodePromptBuilderMixin.build_prompt(owner, messages)
        msg_list = result

        total_cc = 0
        for msg in msg_list:
            content = getattr(msg, "content", None)
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and "cache_control" in block
                    ):
                        total_cc += 1
        # A+B+C = 3 system blocks + 1 history = 4 (exactly at limit)
        assert total_cc <= 4, (
            f"Total cache_control blocks {total_cc} exceeds limit of 4"
        )

    def test_tool_message_as_pre_turn_message(self) -> None:
        """ToolMessage as the pre-turn message does not crash.

        When history trimming cuts off the final AIMessage but leaves
        an earlier tool result in place, the pre-turn message can be
        a ToolMessage.  model_copy() handles this correctly where the
        old __class__(content=...) would crash because ToolMessage
        requires tool_call_id as a constructor arg.
        """
        owner = self._make_claude_owner()
        messages = [
            HumanMessage(content="search for cats"),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "search_web",
                    "args": {"query": "cats"},
                    "id": "call_1",
                }],
            ),
            ToolMessage(
                content="results: many cats found",
                tool_call_id="call_1",
            ),
            HumanMessage(content="now tell me about dogs"),
        ]
        from airunner_services.llm.managers.mixins.node_prompt_builder_mixin import (
            NodePromptBuilderMixin,
        )
        # Must not raise.
        result = NodePromptBuilderMixin.build_prompt(owner, messages)
        msg_list = result
        # Verify the ToolMessage got cache_control (it's the pre-turn
        # message before the last HumanMessage).
        pre_turn = msg_list[-2]
        assert isinstance(pre_turn, ToolMessage), (
            f"Expected ToolMessage at position -2, got "
            f"{pre_turn.__class__.__name__}"
        )
        content = pre_turn.content
        assert isinstance(content, list), (
            "Expected content blocks on ToolMessage"
        )
        assert len(content) > 0, "Expected non-empty content blocks"
        assert content[-1].get("cache_control") == {"type": "ephemeral"}, (
            "ToolMessage missing cache_control marker"
        )
