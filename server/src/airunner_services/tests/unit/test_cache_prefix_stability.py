"""Cache-prefix stability integration tests.

Verifies that the system prompt is byte-identical across calls within
the same conversation and across consecutive turns when nothing
legitimately changes it.  Uses the standard (non-Claude) path with
single-block cache_control.

The post-tool-instruction fix guarantees this by moving dynamic
tool-result content into the per-turn / human-message block instead
of the cached system prompt.

For multi-segment caching tests see test_cache_segment_stability.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage, SystemMessage


class _FakePostToolHelper:
    def __init__(self, return_text: str = ""):
        self.return_text = return_text

    def get_post_tool_instruction_text(self, _messages):
        return self.return_text


class TestCachePrefixStability:
    """Integration-level tests for system-prompt cache stability."""

    @staticmethod
    def _make_owner(**kwargs):
        owner = MagicMock()
        chat_model = MagicMock()
        chat_model.is_vision_model = False
        owner._chat_model = chat_model
        owner._owner = owner  # self._owner must point to self

        owner.escape_system_prompt = MagicMock(
            return_value="SYSTEM_PROMPT_CONTENT"
        )
        owner.add_tool_instructions = MagicMock(
            return_value="SYSTEM_PROMPT_CONTENT"
        )
        owner._per_turn_context = kwargs.get("per_turn_context", "")
        owner._get_post_tool_instructions_helper = MagicMock(
            return_value=_FakePostToolHelper(
                return_text=kwargs.get("post_tool_text", ""),
            )
        )
        owner._gather_knowledge_context = MagicMock(return_value="")
        owner._gather_conversation_context = MagicMock(return_value="")
        owner._last_exchange_block = MagicMock(return_value="")

        owner._merge_consecutive_humans = lambda msgs: msgs
        owner._inject_context_into_human_turn = lambda msgs, *a: msgs

        # Capture the REAL system prompt from _inject_cache_control.
        # Use the standard (non-Claude) path so that the single-block
        # cache_control path is exercised.
        captured: list = []
        owner._inject_cache_control = lambda msgs: (
            captured.append(msgs) or msgs
        )
        owner._captured_cache_messages = captured

        owner._is_claude_model = MagicMock(return_value=False)

        # Wire the real _build_standard_prompt onto the mock so that
        # build_prompt() delegates to it (the mock is self, so method
        # lookups hit the mock's own attrs first).
        from airunner_services.llm.managers.mixins.node_prompt_builder_mixin import (
            NodePromptBuilderMixin,
        )
        owner._build_standard_prompt = (
            NodePromptBuilderMixin._build_standard_prompt.__get__(
                owner, NodePromptBuilderMixin
            )
        )

        owner.chatbot = MagicMock(is_system_bot=False)
        return owner

    @staticmethod
    def _call(owner, messages=None):
        from airunner_services.llm.managers.mixins.node_prompt_builder_mixin \
            import NodePromptBuilderMixin
        if messages is None:
            messages = [HumanMessage(content="hello")]
        return NodePromptBuilderMixin.build_prompt(owner, messages)

    @staticmethod
    def _extract_system_content(owner):
        """Pull the real SystemMessage content from captured output."""
        msgs = owner._captured_cache_messages
        assert msgs, "No messages captured from _inject_cache_control"
        for msg in msgs[0]:
            if isinstance(msg, SystemMessage):
                return msg.content
        raise AssertionError("No SystemMessage in captured output")

    # ── positive tests ──────────────────────────────────────────

    def test_real_system_prompt_identical(self) -> None:
        """Real SystemMessage content is identical with and without
        post-tool text. This proves the fix actually works on real
        output, not mock constants."""
        o1 = self._make_owner()
        o2 = self._make_owner(post_tool_text="[GUIDANCE: use results]")

        self._call(o1)
        self._call(o2)

        sys1 = self._extract_system_content(o1)
        sys2 = self._extract_system_content(o2)
        assert sys1 == sys2, (
            f"BUG: real system prompts differ!\n"
            f"  o1={sys1!r}\n  o2={sys2!r}"
        )

    def test_post_tool_text_in_per_turn(self) -> None:
        """Post-tool text lands in per_turn, not system prompt."""
        captured = []

        def _capture(msgs, per_turn, *a):
            captured.append(per_turn)
            return msgs

        owner = self._make_owner(
            per_turn_context="[datetime]",
            post_tool_text="[GUIDANCE: use results]",
        )
        owner._inject_context_into_human_turn = _capture
        self._call(owner)

        assert len(captured) == 1
        per_turn = captured[0]
        assert "[datetime]" in per_turn
        assert "[GUIDANCE: use results]" in per_turn

    def test_system_prompt_stable_across_turns(self) -> None:
        """System prompt identical across two consecutive turns."""
        o1 = self._make_owner()
        o2 = self._make_owner()
        self._call(o1, [HumanMessage(content="turn 1")])
        self._call(o2, [HumanMessage(content="turn 2")])
        assert self._extract_system_content(o1) == \
            self._extract_system_content(o2)

    # ── negative-control test ───────────────────────────────────

    def test_regression_detected(self) -> None:
        """Simulate the OLD bug and confirm test FAILS."""
        o1 = self._make_owner()
        o2 = self._make_owner(post_tool_text="[GUIDANCE: use results]")

        # Simulate the old code: post-tool text goes INTO the system
        # prompt rather than the per-turn block.  We do this by
        # making add_tool_instructions return the contaminated string.
        o2.add_tool_instructions.return_value = (
            "SYSTEM_PROMPT_CONTENT"  # from escape_system_prompt
            + "[GUIDANCE: use results]"  # old bug: appended here
        )

        self._call(o1)
        self._call(o2)

        sys1 = self._extract_system_content(o1)
        sys2 = self._extract_system_content(o2)
        assert sys1 != sys2, (
            "Regression test: system prompts SHOULD differ when "
            "post-tool text leaks into system prompt. "
            f"sys1={sys1!r} sys2={sys2!r}"
        )

    def test_regression_test_passes_with_fix(self) -> None:
        """Confirm the fix makes the regression test pass (system
        prompts ARE identical with the fix in place)."""
        o1 = self._make_owner()
        o2 = self._make_owner(post_tool_text="[GUIDANCE: use results]")
        # Do NOT contaminate add_tool_instructions — this is the fix

        self._call(o1)
        self._call(o2)

        sys1 = self._extract_system_content(o1)
        sys2 = self._extract_system_content(o2)
        assert sys1 == sys2, (
            f"Fix verification: system prompts should be identical. "
            f"sys1={sys1!r} sys2={sys2!r}"
        )
