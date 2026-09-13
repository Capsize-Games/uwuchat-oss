"""Unit tests for the code-mode agentic-loop framework behavior.

Covers the fixes that let the UwUchat code-mode agent chain tools to
completion instead of narrating after one tool round:

- the agentic iteration guard raises its ceiling for code-mode
  conversations (multi-file coding tasks need many tool cycles),
- the post-tool error instruction steers code-mode recovery toward the
  ACTUAL code tools (list_files, list_registered_projects, ...) instead
  of the async-workflow tools (transition_phase / add_todo_item) that
  are not bound in code mode,
- the shared code-mode detection helper agrees across components.
"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

from langchain_core.messages import ToolMessage

from airunner_services.llm.managers.mixins.node_agentic_guard import (
    NodeAgenticGuard,
)
from airunner_services.llm.managers.mixins.node_post_tool_instructions_helper import (
    NodePostToolInstructionsHelper,
)

_CODE_MODE_STUB = "projects.uwuchat.server.code_mode_service"


class _FakeLogger:
    """No-op logger stub for guard/helper tests."""

    def info(self, *args, **kwargs) -> None:
        """No-op info log."""

    def error(self, *args, **kwargs) -> None:
        """No-op error log."""

    def warning(self, *args, **kwargs) -> None:
        """No-op warning log."""


class _FakeOwner:
    """Minimal owner stub exposing a workflow manager with conv id."""

    def __init__(self) -> None:
        """Create a stub with a workflow manager reporting conv id 7."""
        self.logger = _FakeLogger()
        self._conversation_id = 7


def _code_mode_context(code_mode: bool):
    """Return a context manager that stubs the project code-mode toggle."""
    from contextlib import ExitStack

    stub = ModuleType(_CODE_MODE_STUB)
    stub.code_mode_active_for_owner = lambda owner: code_mode
    stack = ExitStack()
    stack.enter_context(
        patch.dict("os.environ", {"AIRUNNER_PROJECT": "uwuchat"})
    )
    stack.enter_context(patch.dict(sys.modules, {_CODE_MODE_STUB: stub}))
    return stack


# ---------------------------------------------------------------------------
# Agentic iteration ceiling
# ---------------------------------------------------------------------------


def test_code_mode_uses_higher_iteration_ceiling() -> None:
    """A code-mode conversation is not force-stopped at the generic 6
    cycles — it gets the code-mode ceiling instead."""
    from airunner_services.llm.managers.mixins.node_agentic_guard import (
        CODE_MODE_MAX_AGENTIC_ITERATIONS,
    )
    from airunner_services.llm.workflow_manager import MAX_AGENTIC_ITERATIONS

    guard = NodeAgenticGuard(_FakeOwner())
    with _code_mode_context(True):
        assert guard.is_at_max_cycles(
            {"loop_count": MAX_AGENTIC_ITERATIONS}
        ) is False
        assert guard.is_at_max_cycles(
            {"loop_count": CODE_MODE_MAX_AGENTIC_ITERATIONS}
        ) is True


def test_non_code_mode_keeps_generic_ceiling() -> None:
    """A non-code-mode conversation still stops at the generic 6 cycles."""
    guard = NodeAgenticGuard(_FakeOwner())
    with _code_mode_context(False):
        assert guard.is_at_max_cycles({"loop_count": 5}) is False
        assert guard.is_at_max_cycles({"loop_count": 6}) is True


def test_code_mode_detection_falls_back_false_when_project_missing(
    monkeypatch,
) -> None:
    """Without an AIRUNNER_PROJECT, code-mode detection is a no-op and
    the generic ceiling applies."""
    monkeypatch.delenv("AIRUNNER_PROJECT", raising=False)
    guard = NodeAgenticGuard(_FakeOwner())
    assert guard.is_at_max_cycles({"loop_count": 6}) is True


# ---------------------------------------------------------------------------
# Code-mode error recovery instruction
# ---------------------------------------------------------------------------


def test_code_mode_error_uses_code_recovery_not_workflow_tools() -> None:
    """A failed code tool in code mode must steer recovery toward the
    actual code tools, never the async-workflow tools
    (transition_phase / add_todo_item) that aren't bound in code mode."""
    helper = NodePostToolInstructionsHelper(_FakeOwner())
    tool_msgs = [
        ToolMessage(
            content="Error: Path escapes the workspace root",
            tool_call_id="t1",
        ),
    ]
    with _code_mode_context(True):
        result = helper._error_instruction(tool_msgs)
    assert "RECOVER AND RETRY" in result
    assert "list_registered_projects" in result
    assert "transition_phase" not in result
    assert "add_todo_item" not in result


def test_non_code_mode_error_keeps_workflow_instruction() -> None:
    """Outside code mode, an error still yields the async-workflow
    recovery instruction unchanged."""
    helper = NodePostToolInstructionsHelper(_FakeOwner())
    tool_msgs = [
        ToolMessage(
            content="Error: Path escapes the workspace root",
            tool_call_id="t1",
        ),
    ]
    with _code_mode_context(False):
        result = helper._error_instruction(tool_msgs)
    assert "TOOL RETURNED AN ERROR" in result
    assert "transition_phase" in result


def test_stale_error_does_not_poison_later_success() -> None:
    """A stale error earlier in the turn must not trigger the error
    instruction once a LATER tool succeeded — the recovery nudge only
    applies to the most recent tool result."""
    helper = NodePostToolInstructionsHelper(_FakeOwner())
    tool_msgs = [
        ToolMessage(
            content="Error: Path escapes the workspace root",
            tool_call_id="t1",
        ),
        ToolMessage(
            content="File: plans/parallel-tasks/w16-continue2.md ...",
            tool_call_id="t2",
        ),
    ]
    with _code_mode_context(True):
        result = helper._error_instruction(tool_msgs)
    assert result == ""
    with _code_mode_context(False):
        result = helper._error_instruction(tool_msgs)
    assert result == ""


# ---------------------------------------------------------------------------
# Shared code-mode detection helper
# ---------------------------------------------------------------------------


def test_shared_detection_delegates_to_project_module() -> None:
    """code_mode_detection resolves the toggle from the project module."""
    from airunner_services.llm.managers.mixins.code_mode_detection import (
        code_mode_active_for_owner,
    )

    owner = MagicMock()
    with _code_mode_context(True):
        assert code_mode_active_for_owner(owner) is True
    with _code_mode_context(False):
        assert code_mode_active_for_owner(owner) is False


def test_shared_detection_noop_without_project(monkeypatch) -> None:
    """Without AIRUNNER_PROJECT the helper returns False (pure no-op)."""
    from airunner_services.llm.managers.mixins.code_mode_detection import (
        code_mode_active_for_owner,
    )

    monkeypatch.delenv("AIRUNNER_PROJECT", raising=False)
    assert code_mode_active_for_owner(_FakeOwner()) is False
