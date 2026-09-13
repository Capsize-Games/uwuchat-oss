"""Unit tests for WorkflowManager — construction, init chain, and prebind."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Shared helper: construct a WorkflowManager with the heavy init steps mocked
# ---------------------------------------------------------------------------

def _make_workflow_manager(**kwargs):
    """Return a WorkflowManager without running _initialize_model or
    _build_and_compile_workflow (those need DB / LangGraph setup)."""
    with patch(
        "airunner_services.llm.workflow_manager.DatabaseCheckpointSaver"
    ):
        with patch(
            "airunner_services.llm.workflow_manager."
            "WorkflowManager._initialize_model"
        ), patch(
            "airunner_services.llm.workflow_manager."
            "WorkflowManager._build_and_compile_workflow"
        ):
            from airunner_services.llm.workflow_manager import (
                WorkflowManager,
            )

            defaults = {
                "system_prompt": "test prompt",
                "chat_model": MagicMock(),
                "conversation_id": 42,
            }
            defaults.update(kwargs)
            return WorkflowManager(**defaults)


# =========================================================================
# Existing tests: ephemeral flag logic
# =========================================================================


class TestWorkflowManagerConstruction:
    """Regression tests: WorkflowManager(conversation_id=None) must not
    eagerly load any DB conversation state."""

    def test_none_conversation_id_passes_ephemeral_true(self):
        """When conversation_id is None, DatabaseCheckpointSaver receives
        ephemeral=True — prevents the eager, unscoped conversation load."""
        with patch(
            "airunner_services.llm.workflow_manager.DatabaseCheckpointSaver"
        ) as MockSaver:
            mock_saver = MagicMock()
            MockSaver.return_value = mock_saver

            with patch(
                "airunner_services.llm.workflow_manager."
                "WorkflowManager._initialize_model"
            ), patch(
                "airunner_services.llm.workflow_manager."
                "WorkflowManager._build_and_compile_workflow"
            ):
                from airunner_services.llm.workflow_manager import (
                    WorkflowManager,
                )

                WorkflowManager(
                    system_prompt="test",
                    chat_model=MagicMock(),
                    conversation_id=None,
                )

            call_kwargs = MockSaver.call_args[1]
            assert call_kwargs.get("ephemeral") is True, (
                "Expected ephemeral=True when conversation_id is None"
            )

    def test_real_conversation_id_still_passes_ephemeral_false(self):
        """When a real conversation_id is given, canonical behavior is
        preserved — ephemeral is not forced to True."""
        with patch(
            "airunner_services.llm.workflow_manager.DatabaseCheckpointSaver"
        ) as MockSaver:
            mock_saver = MagicMock()
            MockSaver.return_value = mock_saver

            with patch(
                "airunner_services.llm.workflow_manager."
                "WorkflowManager._initialize_model"
            ), patch(
                "airunner_services.llm.workflow_manager."
                "WorkflowManager._build_and_compile_workflow"
            ):
                from airunner_services.llm.workflow_manager import (
                    WorkflowManager,
                )

                WorkflowManager(
                    system_prompt="test",
                    chat_model=MagicMock(),
                    conversation_id=42,
                )

            call_kwargs = MockSaver.call_args[1]
            # ephemeral should not be True for a real conversation id
            assert call_kwargs.get("ephemeral") is not True, (
                "Expected ephemeral to not be True when conversation_id=42"
            )


# =========================================================================
# Cooperative __init__ chain fix — regression tests
# =========================================================================


class TestCooperativeInitChain:
    """Verify every mixin's __init__ runs and sets its attributes."""

    def test_all_mixin_attributes_present_after_construction(self):
        """Every mixin in the MRO must have its attributes set.

        This is a regression test for the bug where ToolManagementMixin
        stopped the cooperative __init__ chain, preventing
        ToolExecutionMixin, WorkflowBuildingMixin, and StreamingMixin
        from initializing.  If a future mixin attribute is added to an
        __init__ but the cooperative chain breaks again, this test will
        fail *at construction time* rather than later as a runtime
        AttributeError in production.
        """
        wm = _make_workflow_manager()

        # --- ToolExecutionMixin attributes ---
        # _prebound_switch_ids: the attribute whose absence caused
        # the production crash this fix addresses.
        assert hasattr(wm, "_prebound_switch_ids"), (
            "_prebound_switch_ids missing — "
            "ToolExecutionMixin.__init__ did not run"
        )
        assert wm._prebound_switch_ids == set(), (
            f"_prebound_switch_ids should be empty set, "
            f"got {wm._prebound_switch_ids!r}"
        )

        # _discovered_tools: previously had a manual workaround in
        # WorkflowManager.__init__ because the chain was broken.
        assert hasattr(wm, "_discovered_tools"), (
            "_discovered_tools missing — "
            "ToolExecutionMixin.__init__ did not run"
        )
        assert wm._discovered_tools == set(), (
            f"_discovered_tools should be empty set, "
            f"got {wm._discovered_tools!r}"
        )

        # _executed_tools is set by ToolExecutionMixin then
        # overwritten by WorkflowManager — confirm presence.
        assert hasattr(wm, "_executed_tools"), (
            "_executed_tools missing"
        )
        assert wm._executed_tools == [], (
            f"_executed_tools should be empty list, "
            f"got {wm._executed_tools!r}"
        )

        # --- WorkflowBuildingMixin attributes ---
        assert hasattr(wm, "_workflow"), (
            "_workflow missing — "
            "WorkflowBuildingMixin.__init__ did not run"
        )
        assert wm._workflow is None, (
            f"_workflow should be None before build, "
            f"got {wm._workflow!r}"
        )

        # --- StreamingMixin attributes ---
        assert hasattr(wm, "_thread_id"), (
            "_thread_id missing — StreamingMixin.__init__ did not run"
        )

        # --- ToolManagementMixin attributes ---
        # _chat_model is set by ToolManagementMixin then overwritten
        # by WorkflowManager.__init__ — confirm it is the WorkflowManager
        # value (the actual chat_model mock, not None).
        assert hasattr(wm, "_chat_model"), (
            "_chat_model missing — "
            "ToolManagementMixin.__init__ did not run"
        )
        assert wm._chat_model is not None, (
            "_chat_model should be the mock passed to constructor, "
            "not None (WorkflowManager must overwrite mixin default)"
        )

    def test_prebind_for_pending_category_switch_does_not_crash(self):
        """Direct repro of the original AttributeError crash.

        Before the cooperative __init__ fix, constructing a
        WorkflowManager and calling _prebind_for_pending_category_switch
        would raise::

            AttributeError: 'WorkflowManager' object has no
            attribute '_prebound_switch_ids'

        After the fix the call completes cleanly and the switch call ID
        is recorded in _prebound_switch_ids.
        """
        wm = _make_workflow_manager()

        # Give the instance a mock ToolManager so _rebind_for_category
        # (called by the prebind path) has something to work with.
        wm._tool_manager = MagicMock()
        fake_tool = MagicMock()
        fake_tool.name = "list_tool_categories"
        fake_switch = MagicMock()
        fake_switch.name = "switch_tool_category"
        wm._tools = [fake_switch, fake_tool]

        # Mock _enabled_category_descriptions (imported inside the
        # method from orchestration_tools) to return a dict containing
        # the category we'll use in the synthetic tool call.
        with patch(
            "airunner_services.llm.tools.orchestration_tools."
            "_enabled_category_descriptions",
            return_value={"knowledge": "Knowledge tools"},
        ):
            # Mock _rebind_for_category on the instance so we don't
            # need a real ToolManager pipeline behind it.
            wm._rebind_for_category = MagicMock()

            tool_calls = [
                {
                    "name": "switch_tool_category",
                    "id": "switch-1",
                    "args": {"category": "knowledge"},
                },
            ]

            # This is the call that used to crash with AttributeError.
            wm._prebind_for_pending_category_switch(tool_calls)

        # After a successful prebind the switch call ID must be
        # recorded in _prebound_switch_ids.
        assert "switch-1" in wm._prebound_switch_ids, (
            "Expected 'switch-1' in _prebound_switch_ids after prebind, "
            f"got {wm._prebound_switch_ids!r}"
        )

        # _rebind_for_category must have been called with the correct
        # category.
        wm._rebind_for_category.assert_called_once()
        from airunner_services.llm.core.tool_registry import ToolCategory

        call_arg = wm._rebind_for_category.call_args[0][0]
        assert call_arg == ToolCategory.KNOWLEDGE, (
            f"Expected ToolCategory.KNOWLEDGE, got {call_arg!r}"
        )
