"""Multi-segment cache-breakpoint stability tests.

Verifies that the three-volatility-tier segmentation (Segment A/B/C)
produces the expected cache_control blocks and that segment A stays
byte-identical when tier or risk changes while segment C varies.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage, SystemMessage
from airunner_services.conf.model_settings import CLAUDE_HAIKU_MODEL


class _FakePostToolHelper:
    def __init__(self, return_text: str = ""):
        self.return_text = return_text

    def get_post_tool_instruction_text(self, _messages):
        return self.return_text


class TestCacheSegmentStability:
    """Unit tests for multi-breakpoint Anthropic prompt caching."""

    @staticmethod
    def _make_claude_owner(
        seg_a_parts=None, seg_b_parts=None, seg_c_parts=None,
        per_turn_context="", post_tool_text="",
    ):
        """Return a mock owner wired for the Claude segmented path."""
        from airunner_services.llm.managers.prompt_builder.parts import (
            PromptSegments,
        )

        segments = PromptSegments(
            segment_a=list(seg_a_parts or []),
            segment_b=list(seg_b_parts or []),
            segment_c=list(seg_c_parts or []),
        )

        owner = MagicMock()
        chat_model = MagicMock()
        chat_model.is_vision_model = False
        chat_model.model = CLAUDE_HAIKU_MODEL
        owner._chat_model = chat_model
        owner._owner = owner

        # Store segments directly on the owner — this is what
        # _build_claude_prompt reads (set by apply_workflow_request_setup
        # in production).
        owner._prompt_segments = segments
        owner._per_turn_context = per_turn_context
        owner._get_post_tool_instructions_helper = MagicMock(
            return_value=_FakePostToolHelper(
                return_text=post_tool_text,
            )
        )
        owner._gather_knowledge_context = MagicMock(return_value="")
        owner._gather_conversation_context = MagicMock(return_value="")

        owner._merge_consecutive_humans = lambda msgs: msgs
        owner._inject_context_into_human_turn = lambda msgs, *a: msgs

        # Wire the real _build_claude_prompt onto the mock so that
        # build_prompt() delegates to it (the mock is self, so method
        # lookups hit the mock's own attrs first).
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
        # _build_segmented_system_msg is a @staticmethod — set it
        # directly so the mock resolves it.
        owner._build_segmented_system_msg = (
            NodePromptBuilderMixin._build_segmented_system_msg
        )
        # _inject_history_cache_control is in NodePromptCacheMixin
        # (ancestor of NodePromptBuilderMixin).
        owner._inject_history_cache_control = (
            NodePromptBuilderMixin._inject_history_cache_control.__get__(
                owner, NodePromptBuilderMixin
            )
        )
        # Quiet the no-op logger
        owner.logger = MagicMock()

        owner.chatbot = MagicMock(is_system_bot=False)
        return owner, segments

    @staticmethod
    def _call_build_prompt(owner, messages=None):
        """Call build_prompt and return the message list."""
        from airunner_services.llm.managers.mixins.node_prompt_builder_mixin import (
            NodePromptBuilderMixin,
        )
        if messages is None:
            messages = [HumanMessage(content="hello")]
        result = NodePromptBuilderMixin.build_prompt(owner, messages)
        if hasattr(result, "to_messages"):
            return result.to_messages()
        return result

    @staticmethod
    def _extract_system_content_blocks(owner, messages=None):
        """Extract the list of content blocks from the SystemMessage."""
        msgs = TestCacheSegmentStability._call_build_prompt(
            owner, messages
        )
        for msg in msgs:
            if isinstance(msg, SystemMessage):
                return msg.content
        raise AssertionError("No SystemMessage in result")

    # ── Segment A stability ─────────────────────────────────────

    def test_segment_a_stable_across_tier_change(self) -> None:
        """Segment A content is identical when tier changes."""
        owner1, _ = self._make_claude_owner(
            seg_a_parts=["IDENTITY: test bot"],
            seg_b_parts=["HARD RULES"],
            seg_c_parts=["base tier core rules"],
        )
        owner2, _ = self._make_claude_owner(
            seg_a_parts=["IDENTITY: test bot"],
            seg_b_parts=["HARD RULES"],
            seg_c_parts=["standard tier: memory, style, ui"],
        )

        blocks1 = self._extract_system_content_blocks(owner1)
        blocks2 = self._extract_system_content_blocks(owner2)

        assert len(blocks1) >= 2, (
            f"Expected at least 2 blocks, got {len(blocks1)}"
        )
        assert len(blocks2) >= 2, (
            f"Expected at least 2 blocks, got {len(blocks2)}"
        )

        text_a1 = blocks1[0]["text"]
        text_a2 = blocks2[0]["text"]
        assert text_a1 == text_a2, (
            f"Segment A must be identical across tier changes:\n"
            f"  A1={text_a1!r}\n  A2={text_a2!r}"
        )
        # Segment C text should differ
        if len(blocks1) >= 3 and len(blocks2) >= 3:
            text_c1 = blocks1[2]["text"]
            text_c2 = blocks2[2]["text"]
            assert text_c1 != text_c2, (
                "Segment C must differ when tier changes"
            )

    def test_segment_a_stable_across_risk_change(self) -> None:
        """Segment A content is identical when risk-tier toggles
        segment B on/off."""
        owner1, _ = self._make_claude_owner(
            seg_a_parts=["IDENTITY: test bot"],
            seg_b_parts=["HARD RULES"],
            seg_c_parts=["style block"],
        )
        owner2, _ = self._make_claude_owner(
            seg_a_parts=["IDENTITY: test bot"],
            seg_b_parts=[],  # risk=innocuous → no hard rules
            seg_c_parts=["style block"],
        )

        blocks1 = self._extract_system_content_blocks(owner1)
        blocks2 = self._extract_system_content_blocks(owner2)

        text_a1 = blocks1[0]["text"]
        text_a2 = blocks2[0]["text"]
        assert text_a1 == text_a2, (
            f"Segment A must be identical across risk changes:\n"
            f"  A1={text_a1!r}\n  A2={text_a2!r}"
        )

    def test_segment_c_changes_with_tier_a_stable(self) -> None:
        """Explicit check: Segment A is byte-identical, Segment C
        changes when tier flips from base to standard."""
        owner_base, _ = self._make_claude_owner(
            seg_a_parts=["IDENTITY: bot"],
            seg_b_parts=[],
            seg_c_parts=["base: core rules only"],
        )
        owner_std, _ = self._make_claude_owner(
            seg_a_parts=["IDENTITY: bot"],
            seg_b_parts=[],
            seg_c_parts=["standard: memory + style + ui"],
        )

        blocks_base = self._extract_system_content_blocks(owner_base)
        blocks_std = self._extract_system_content_blocks(owner_std)

        a_base = blocks_base[0]["text"]
        a_std = blocks_std[0]["text"]
        assert a_base == a_std, "Segment A must be identical"

        c_base = blocks_base[-1]["text"]
        c_std = blocks_std[-1]["text"]
        assert c_base != c_std, (
            "Segment C must differ when tier changes"
        )

    # ── cache_control block count ────────────────────────────────

    def test_cache_control_blocks_present(self) -> None:
        """Every content block in the SystemMessage has a
        cache_control marker."""
        owner, _ = self._make_claude_owner(
            seg_a_parts=["IDENTITY: bot"],
            seg_b_parts=["HARD RULES"],
            seg_c_parts=["style block"],
        )
        blocks = self._extract_system_content_blocks(owner)

        assert isinstance(blocks, list), (
            f"Expected list of blocks, got {type(blocks)}"
        )
        assert len(blocks) == 3, (
            f"Expected 3 blocks (A, B, C), got {len(blocks)}"
        )
        for i, block in enumerate(blocks):
            assert block.get("type") == "text", (
                f"Block {i}: expected type=text, got {block.get('type')}"
            )
            cc = block.get("cache_control")
            assert cc is not None, (
                f"Block {i}: missing cache_control"
            )
            assert cc.get("type") == "ephemeral", (
                f"Block {i}: expected ephemeral, got {cc.get('type')}"
            )

    def test_empty_segment_b_skipped(self) -> None:
        """When segment B is empty, only 2 blocks (A + C) are emitted."""
        owner, _ = self._make_claude_owner(
            seg_a_parts=["IDENTITY: bot"],
            seg_b_parts=[],   # empty — should be skipped
            seg_c_parts=["style block"],
        )
        blocks = self._extract_system_content_blocks(owner)

        assert len(blocks) == 2, (
            f"Expected 2 blocks (A + C), got {len(blocks)}"
        )
        # Block 0 should be A, block 1 should be C
        assert "IDENTITY: bot" in blocks[0]["text"]
        assert "style block" in blocks[1]["text"]

    def test_empty_segments_b_and_c_both_skipped(self) -> None:
        """When both B and C are empty, only segment A is emitted."""
        owner, _ = self._make_claude_owner(
            seg_a_parts=["IDENTITY: solo bot"],
            seg_b_parts=[],
            seg_c_parts=[],
        )
        blocks = self._extract_system_content_blocks(owner)

        assert len(blocks) == 1, (
            f"Expected 1 block (A only), got {len(blocks)}"
        )
        assert "IDENTITY: solo bot" in blocks[0]["text"]

    # ── action-threading & end-to-end tests ──────────────────────

    def test_action_reaches_segments_via_workflow_setup(self) -> None:
        """Verify that apply_workflow_request_setup stores segments
        computed with the real per-turn action — not a hardcoded one.

        This is the test that would have caught the hardcoded
        APPLICATION_COMMAND bug.
        """
        from airunner_services.contract_enums import LLMActionType

        owner = MagicMock()
        wm = MagicMock()
        owner._workflow_manager = wm

        # _build_base_prompt_segments captures the action it receives
        captured_actions: list = []

        def fake_segments(action):
            captured_actions.append(action)
            from airunner_services.llm.managers.prompt_builder.prompt_segments import (
                PromptSegments,
            )
            seg = PromptSegments()
            seg.segment_a.append(f"action={action.value}")
            return seg

        owner._build_base_prompt_segments = fake_segments

        from airunner_services.llm.managers.mixins.generation_workflow_support import (
            apply_workflow_request_setup,
        )

        # Simulate a DIALOGUE (CHAT) call in conversational mode
        # with no force_tool — this is the segmentable path.
        req = MagicMock()
        req.tool_categories = None  # conversational default
        req.force_tool = None
        apply_workflow_request_setup(
            owner,
            action=LLMActionType.CHAT,
            action_system_prompt="fake prompt",
            skip_tool_setup=False,
            request_setup=req,
            system_prompt=None,
        )

        assert len(captured_actions) == 1, (
            f"_build_base_prompt_segments should be called once, "
            f"was called {len(captured_actions)} times"
        )
        assert captured_actions[0] == LLMActionType.CHAT, (
            f"Expected action=CHAT, got {captured_actions[0]}"
        )

        # The workflow manager should have received the segments
        wm.update_prompt_segments.assert_called_once()
        stored = wm.update_prompt_segments.call_args[0][0]
        assert stored.segment_a[0] == "action=RESPOND: Choose this " \
            "action if you want to respond to the user."

    def test_custom_prompt_skips_segmentation(self) -> None:
        """When a custom system_prompt is provided, segments are set
        to None (not just skipped) to clear any stale segments from a
        previous turn."""
        from airunner_services.llm.managers.mixins.generation_workflow_support import (
            apply_workflow_request_setup,
        )
        from airunner_services.contract_enums import LLMActionType

        owner = MagicMock()
        wm = MagicMock()
        owner._workflow_manager = wm

        apply_workflow_request_setup(
            owner,
            action=LLMActionType.CHAT,
            action_system_prompt="custom augmented prompt",
            skip_tool_setup=False,
            request_setup=MagicMock(),
            system_prompt="custom user prompt",
        )

        # Must have called with None to clear stale segments
        wm.update_prompt_segments.assert_called_once_with(None)

    def test_force_tool_clears_segments(self) -> None:
        """When force_tool is set, segments are cleared (None) so the
        Claude path falls back to the flat single-block string that
        includes get_force_tool_instruction()."""
        from airunner_services.llm.managers.mixins.generation_workflow_support import (
            apply_workflow_request_setup,
        )
        from airunner_services.contract_enums import LLMActionType

        owner = MagicMock()
        wm = MagicMock()
        owner._workflow_manager = wm

        req = MagicMock()
        req.tool_categories = None
        req.force_tool = "start_workflow"

        apply_workflow_request_setup(
            owner,
            action=LLMActionType.CHAT,
            action_system_prompt="prompt with force tool instruction",
            skip_tool_setup=False,
            request_setup=req,
            system_prompt=None,
        )

        # Segments must be cleared — force_tool changes prompt content
        wm.update_prompt_segments.assert_called_once_with(None)

    def test_math_mode_clears_segments(self) -> None:
        """When mode is 'math', segments are cleared because the flat
        prompt uses MATH_SYSTEM_PROMPT, not build_base_prompt_parts."""
        from airunner_services.llm.managers.mixins.generation_workflow_support import (
            apply_workflow_request_setup,
        )
        from airunner_services.contract_enums import LLMActionType
        from airunner_services.llm.core.tool_registry import ToolCategory

        owner = MagicMock()
        wm = MagicMock()
        owner._workflow_manager = wm

        req = MagicMock()
        req.tool_categories = [ToolCategory.MATH]
        req.force_tool = None

        apply_workflow_request_setup(
            owner,
            action=LLMActionType.CHAT,
            action_system_prompt="math system prompt",
            skip_tool_setup=False,
            request_setup=req,
            system_prompt=None,
        )

        wm.update_prompt_segments.assert_called_once_with(None)

    def test_precision_mode_clears_segments(self) -> None:
        """When mode is 'precision', segments are cleared because the
        flat prompt uses PRECISION_SYSTEM_PROMPT."""
        from airunner_services.llm.managers.mixins.generation_workflow_support import (
            apply_workflow_request_setup,
        )
        from airunner_services.contract_enums import LLMActionType
        from airunner_services.llm.core.tool_registry import ToolCategory

        owner = MagicMock()
        wm = MagicMock()
        owner._workflow_manager = wm

        req = MagicMock()
        req.tool_categories = [ToolCategory.ANALYSIS]
        req.force_tool = None

        apply_workflow_request_setup(
            owner,
            action=LLMActionType.CHAT,
            action_system_prompt="precision system prompt",
            skip_tool_setup=False,
            request_setup=req,
            system_prompt=None,
        )

        wm.update_prompt_segments.assert_called_once_with(None)

    def test_conversational_no_force_tool_still_segments(self) -> None:
        """The plain conversational default with no force_tool is the
        ONLY branch where segments are stored."""
        from airunner_services.llm.managers.mixins.generation_workflow_support import (
            apply_workflow_request_setup,
        )
        from airunner_services.contract_enums import LLMActionType

        owner = MagicMock()
        wm = MagicMock()
        owner._workflow_manager = wm

        captured_actions = []

        def fake_segments(action):
            captured_actions.append(action)
            from airunner_services.llm.managers.prompt_builder.prompt_segments import (
                PromptSegments,
            )
            return PromptSegments(
                segment_a=["identity: test"],
            )

        owner._build_base_prompt_segments = fake_segments

        req = MagicMock()
        req.tool_categories = None  # conversational
        req.force_tool = None

        apply_workflow_request_setup(
            owner,
            action=LLMActionType.CHAT,
            action_system_prompt="conversational prompt",
            skip_tool_setup=False,
            request_setup=req,
            system_prompt=None,
        )

        assert len(captured_actions) == 1
        assert captured_actions[0] == LLMActionType.CHAT
        # Must have stored real segments (not None)
        wm.update_prompt_segments.assert_called_once()
        stored = wm.update_prompt_segments.call_args[0][0]
        assert stored.segment_a == ["identity: test"]

    def test_claude_path_cache_prefix_stable(self) -> None:
        """Claude segmented path produces stable SystemMessage content
        across two turns when segments are identical.  This is the
        Claude-path equivalent of test_system_prompt_stable_across_turns
        in the standard-path tests."""
        from airunner_services.llm.managers.prompt_builder.prompt_segments import (
            PromptSegments,
        )

        PromptSegments(
            segment_a=["IDENTITY: test"],
            segment_b=["HARD RULES"],
            segment_c=["style block"],
        )

        owner1, _ = self._make_claude_owner(
            seg_a_parts=["IDENTITY: test"],
            seg_b_parts=["HARD RULES"],
            seg_c_parts=["style block"],
        )
        owner2, _ = self._make_claude_owner(
            seg_a_parts=["IDENTITY: test"],
            seg_b_parts=["HARD RULES"],
            seg_c_parts=["style block"],
        )

        blocks1 = self._extract_system_content_blocks(
            owner1, [HumanMessage(content="turn 1")]
        )
        blocks2 = self._extract_system_content_blocks(
            owner2, [HumanMessage(content="turn 2")]
        )

        assert len(blocks1) == len(blocks2), (
            f"Block count differs: {len(blocks1)} vs {len(blocks2)}"
        )
        for i, (b1, b2) in enumerate(zip(blocks1, blocks2)):
            assert b1["text"] == b2["text"], (
                f"Block {i} text differs between turns:\n"
                f"  T1={b1['text']!r}\n  T2={b2['text']!r}"
            )
            assert b1["cache_control"] == b2["cache_control"], (
                f"Block {i} cache_control differs between turns"
            )

    # ── byte-for-byte equivalence proof ──────────────────────────

    def test_segments_equal_flat_prompt_byte_for_byte(self) -> None:
        """Proof: segments + ACTION_MODE_PROMPTS appended to segment_c
        produces the exact same string as get_system_prompt_with_context
        for conversational/no-force_tool — across actions and tiers.

        This mirrors what apply_workflow_request_setup does in
        production: builds segments, appends the mode prompt to
        segment_c, then stores.  The joined result must byte-match
        the flat string that get_system_prompt_with_context returns.
        """
        from unittest.mock import patch
        from airunner_services.contract_enums import LLMActionType
        from airunner_services.llm.managers.mixins.system_prompt_action_text import (
            ACTION_MODE_PROMPTS,
        )
        from airunner_services.llm.managers.prompt_builder.prompt_segments import (
            build_base_prompt_segments,
        )
        from airunner_services.llm.managers.prompt_builder.actions import (
            get_system_prompt_with_context,
        )

        def _make_owner():
            owner = MagicMock()
            chatbot = MagicMock()
            chatbot.is_system_bot = False
            chatbot.id = None
            chatbot.botname = "T"
            chatbot.bot_personality = None
            chatbot.use_personality = True
            chatbot.output_language = None
            chatbot.knowledge_mode = "omniscient"
            chatbot.species_data = {}
            chatbot.identity_core = {}
            chatbot.inner_state = None
            chatbot.language_proficiency = "fluent"
            chatbot.attributes = {}
            chatbot.speech_patterns = ""
            chatbot.backstory = ""
            chatbot.gender = ""
            chatbot.avatar_emoji = ""
            chatbot.location = {"home_description": "U"}
            chatbot.language = {}
            owner.chatbot = chatbot
            owner.language_settings = MagicMock(
                user_language="en", bot_language="en"
            )
            owner._risk_tier = "moderate"
            owner._tools = []
            owner.user = MagicMock(username="U")
            owner.llm_settings = MagicMock(
                include_health_disclaimer=True
            )
            return owner

        actions = (LLMActionType.CHAT, LLMActionType.GENERATE_IMAGE)
        tiers = ("base", "full")

        for action in actions:
            for tier_name in tiers:
                owner = _make_owner()
                with (
                    patch(
                        "airunner_services.llm.managers"
                        ".prompt_builder.parts._agent_memory_part",
                        return_value=None,
                    ),
                    patch(
                        "airunner_services.llm.managers"
                        ".prompt_builder.parts"
                        "._episodic_summary_part",
                        return_value=None,
                    ),
                    patch(
                        "airunner_services.llm.managers"
                        ".prompt_builder.parts._ui_context_part",
                        return_value=None,
                    ),
                    patch(
                        "airunner_services.llm.managers"
                        ".prompt_builder.parts._style_part",
                        return_value="[STYLE GUIDELINES]",
                    ),
                    patch(
                        "airunner_services.llm.managers"
                        ".prompt_builder.parts._prompt_tier",
                        return_value=tier_name,
                    ),
                ):
                    flat = get_system_prompt_with_context(
                        owner, action,
                        tool_categories=None, force_tool=None,
                    )
                    segments = build_base_prompt_segments(
                        owner, action
                    )
                    # Mirror apply_workflow_request_setup: append
                    # the mode prompt to segment_c.
                    mode_text = ACTION_MODE_PROMPTS.get(action, "")
                    if mode_text:
                        segments.segment_c.append(
                            mode_text.lstrip("\n")
                        )
                    seg_joined = "\n\n".join(segments.all_parts())

                    assert seg_joined == flat, (
                        f"Mismatch for action={action} tier={tier_name}:\n"
                        f"  segments ({len(seg_joined)} chars): "
                        f"{seg_joined[:120]!r}...\n"
                        f"  flat    ({len(flat)} chars): "
                        f"{flat[:120]!r}..."
                    )
