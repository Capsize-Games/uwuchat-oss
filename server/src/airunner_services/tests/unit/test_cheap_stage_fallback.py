"""Tests for the cheap-stage fallback logging in
_maybe_run_tool_execution_stage.

When the TOOL_EXECUTION cheap stage silently degrades to the expensive
DIALOGUE path (because _specialized_chat_models is missing the key,
the project module can't be imported, or conversation_id / tool_manager
are absent), a warning log MUST be emitted so the operator can diagnose
why tool calls are running on the expensive model.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestCheapStageFallbackLogging:
    """Verify that each silent bail-out path in
    _maybe_run_tool_execution_stage emits a warning log."""

    @staticmethod
    def _call_stage(owner: MagicMock, prompt: str,
                    selected_categories: list[str],
                    llm_request: MagicMock) -> object:
        """Import and invoke the method-under-test."""
        from airunner_services.llm.managers.mixins.request_handling_mixin \
            import RequestHandlingMixin

        return RequestHandlingMixin._maybe_run_tool_execution_stage(
            owner, prompt, selected_categories, llm_request,
        )

    # ── missing TOOL_EXECUTION model ─────────────────────────────

    def test_warns_when_no_specialized_models_attr(self) -> None:
        """Warns when _specialized_chat_models attribute is missing."""
        owner = MagicMock()
        # AttributeError → getattr returns the default {}
        del owner._specialized_chat_models

        result = self._call_stage(
            owner, "test prompt", ["search"], MagicMock(),
        )

        assert result is None
        owner.logger.warning.assert_called_once()
        call_arg = owner.logger.warning.call_args[0][0]
        assert "no TOOL_EXECUTION model" in call_arg

    def test_warns_when_toolexecution_key_missing(self) -> None:
        """Warns when _specialized_chat_models exists but TOOL_EXECUTION
        key is absent."""
        owner = MagicMock()
        owner._specialized_chat_models = {
            "TOOL_CLASSIFICATION": MagicMock(),
            "DIALOGUE": MagicMock(),
        }

        result = self._call_stage(
            owner, "test prompt", ["search"], MagicMock(),
        )

        assert result is None
        owner.logger.warning.assert_called_once()
        call_args = owner.logger.warning.call_args[0]
        format_string = call_args[0]
        assert "no TOOL_EXECUTION model" in format_string
        # The available-keys list is the second positional arg
        assert len(call_args) >= 2
        assert "TOOL_CLASSIFICATION" in call_args[1]

    def test_warns_when_specialized_models_is_empty_dict(self) -> None:
        """Warns when _specialized_chat_models is an empty dict."""
        owner = MagicMock()
        owner._specialized_chat_models = {}

        result = self._call_stage(
            owner, "test prompt", ["search"], MagicMock(),
        )

        assert result is None
        owner.logger.warning.assert_called_once()
        call_arg = owner.logger.warning.call_args[0][0]
        assert "no TOOL_EXECUTION model" in call_arg

    # ── missing conversation context ─────────────────────────────

    def test_warns_when_no_conversation_id(self) -> None:
        """Warns when conversation_id is missing."""
        owner = MagicMock()
        owner._specialized_chat_models = {
            "TOOL_EXECUTION": MagicMock(),
        }
        # Workflow manager exists but has no _conversation_id
        wm = MagicMock(spec=object)
        del wm._conversation_id  # AttributeError → getattr returns None
        owner._workflow_manager = wm
        owner._tool_manager = MagicMock()

        # We need to mock the import so we don't hit an ImportError
        import sys
        fake_mod = MagicMock()
        fake_mod.run_tool_execution_stage = MagicMock()
        sys.modules[
            "projects.uwuchat.server.tool_execution_stage"
        ] = fake_mod

        try:
            result = self._call_stage(
                owner, "test prompt", ["search"], MagicMock(),
            )
        finally:
            del sys.modules[
                "projects.uwuchat.server.tool_execution_stage"
            ]

        assert result is None
        owner.logger.warning.assert_called_once()
        call_arg = owner.logger.warning.call_args[0][0]
        assert "conversation_id" in call_arg

    def test_warns_when_no_tool_manager(self) -> None:
        """Warns when _tool_manager is missing."""
        owner = MagicMock()
        owner._specialized_chat_models = {
            "TOOL_EXECUTION": MagicMock(),
        }
        wm = MagicMock()
        wm._conversation_id = 42
        owner._workflow_manager = wm
        owner._tool_manager = None

        import sys
        fake_mod = MagicMock()
        fake_mod.run_tool_execution_stage = MagicMock()
        sys.modules[
            "projects.uwuchat.server.tool_execution_stage"
        ] = fake_mod

        try:
            result = self._call_stage(
                owner, "test prompt", ["search"], MagicMock(),
            )
        finally:
            del sys.modules[
                "projects.uwuchat.server.tool_execution_stage"
            ]

        assert result is None
        owner.logger.warning.assert_called_once()
        call_arg = owner.logger.warning.call_args[0][0]
        assert "tool_manager" in call_arg

    # ── ImportError path ─────────────────────────────────────────

    def test_warns_when_module_import_fails(self) -> None:
        """Warns when tool_execution_stage module cannot be imported."""
        owner = MagicMock()
        owner._specialized_chat_models = {
            "TOOL_EXECUTION": MagicMock(),
        }

        # Ensure the module is NOT importable
        import sys
        sys.modules.pop(
            "projects.uwuchat.server.tool_execution_stage", None
        )

        # Force ImportError by patching importlib.import_module
        import importlib
        original_import = importlib.import_module

        def _raise_import_error(name: str, package=None):
            raise ImportError(f"No module named '{name}'")

        importlib.import_module = _raise_import_error

        try:
            result = self._call_stage(
                owner, "test prompt", ["search"], MagicMock(),
            )
        finally:
            importlib.import_module = original_import

        assert result is None
        owner.logger.warning.assert_called_once()
        call_arg = owner.logger.warning.call_args[0][0]
        assert "could not import" in call_arg.lower()

    # ── happy path (no warning) ──────────────────────────────────

    def test_no_warning_on_successful_stage_run(self) -> None:
        """When all preconditions are met, the stage runs and returns
        its result without emitting a warning."""
        owner = MagicMock()
        owner._specialized_chat_models = {
            "TOOL_EXECUTION": MagicMock(),
        }
        wm = MagicMock()
        wm._conversation_id = 42
        owner._workflow_manager = wm
        owner._tool_manager = MagicMock()

        import sys
        fake_mod = MagicMock()
        fake_mod.run_tool_execution_stage = MagicMock(
            return_value={"tools_executed": True},
        )
        sys.modules[
            "projects.uwuchat.server.tool_execution_stage"
        ] = fake_mod

        try:
            result = self._call_stage(
                owner, "test prompt", ["search"], MagicMock(),
            )
        finally:
            del sys.modules[
                "projects.uwuchat.server.tool_execution_stage"
            ]

        assert result is not None
        assert result == {"tools_executed": True}
        # No warnings should have been emitted
        owner.logger.warning.assert_not_called()
