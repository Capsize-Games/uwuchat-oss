"""Regression tests for cheap-stage hint routing.

Covers: the extractable _set_cheap_stage_hint method (prevents
system_prompt mutation) and the setup_generation_workflow boundary
(prevents the custom-prompt path from being taken when it shouldn't).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from airunner_services.contract_enums import LLMActionType

_PER_TURN_PATH = (
    "airunner_services.llm.managers.prompt_builder."
    "per_turn_context.collect_per_turn_context"
)


class TestSetCheapStageHint:
    """Tests for the extracted _set_cheap_stage_hint method."""

    @staticmethod
    def _call(stage_outcome: dict, owner=None):
        from airunner_services.llm.managers.mixins.request_handling_mixin \
            import RequestHandlingMixin
        if owner is None:
            owner = MagicMock()
        RequestHandlingMixin._set_cheap_stage_hint(owner, stage_outcome)
        return owner

    def test_no_op_on_empty_outcome(self) -> None:
        """Empty stage_outcome sets nothing."""
        owner = self._call({})
        assert getattr(owner, "_cheap_stage_hint", None) is None

    def test_sets_hint_for_clarification(self) -> None:
        """Clarification note → _cheap_stage_hint is set."""
        owner = self._call({
            "clarification_note": "need a date",
        })
        assert owner._cheap_stage_hint is not None
        assert "need a date" in owner._cheap_stage_hint

    def test_sets_hint_for_tool_results(self) -> None:
        """Tool results → _cheap_stage_hint is set."""
        owner = self._call({
            "tools_executed": True,
            "tool_results": ["search_news: found 5 articles"],
        })
        assert owner._cheap_stage_hint is not None
        assert "search_news: found 5 articles" in owner._cheap_stage_hint

    def test_does_not_set_system_prompt(self) -> None:
        """_set_cheap_stage_hint does NOT touch system_prompt."""
        # Use a plain object so hasattr/getattr work predictably
        class FakeOwner:
            pass
        owner = FakeOwner()
        self._call(
            {"clarification_note": "need a date",
             "tool_results": ["search_news: found 5"]},
            owner=owner,
        )
        # The old bug did system_prompt = (system_prompt or "") + hint.
        # The new code only sets _cheap_stage_hint.
        assert not hasattr(owner, "system_prompt")
        assert owner._cheap_stage_hint is not None

    def test_both_clarification_and_tool_results(self) -> None:
        """Both clarification and tool results → combined hint."""
        owner = self._call({
            "clarification_note": "need a date",
            "tool_results": ["calc: 12.53"],
        })
        hint = owner._cheap_stage_hint
        assert "need a date" in hint
        assert "calc: 12.53" in hint


class TestSetupGenerationWorkflowWithHint:
    """Tests that setup_generation_workflow takes the full identity
    path when system_prompt is None (with hint in per-turn)."""

    async def test_full_path_taken_with_none_system_prompt(self) -> None:
        """With system_prompt=None, get_system_prompt_with_context is
        called (full identity), NOT _augment_custom_system_prompt."""
        from airunner_services.llm.managers.mixins.generation_workflow_support \
            import setup_generation_workflow

        wm = MagicMock()
        owner = MagicMock()
        owner._workflow_manager = wm
        owner._active_rag_context = None
        owner._cheap_stage_hint = "[tool result: found it]"

        # Mock the two branches so we can assert which one executes.
        owner._augment_custom_system_prompt = MagicMock(
            return_value="CUSTOM_PATH_RESULT"
        )
        owner.get_system_prompt_with_context = MagicMock(
            return_value="FULL_PATH_RESULT"
        )

        llm_request = MagicMock()
        llm_request.system_prompt = None

        with patch(
            _PER_TURN_PATH,
            new=AsyncMock(return_value="[datetime: ...]"),
        ):
            result = await setup_generation_workflow(
                owner,
                action=LLMActionType.CHAT,
                system_prompt=None,
                llm_request=llm_request,
            )

        # Full identity path was taken, NOT the custom path
        assert owner.get_system_prompt_with_context.called, (
            "BUG: full identity path was NOT called"
        )
        assert not owner._augment_custom_system_prompt.called, (
            "BUG: custom prompt path was taken instead of full path"
        )
        # Hint is NOT in the system prompt
        assert "FULL_PATH_RESULT" in result or result == "FULL_PATH_RESULT"
        # Hint IS in per_turn_context
        assert "[tool result: found it]" in wm._per_turn_context
