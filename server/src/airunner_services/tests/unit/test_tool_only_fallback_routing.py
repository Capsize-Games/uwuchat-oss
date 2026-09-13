"""Tests for code-mode command-tool routing in _tool_only_fallback.

Covers the round-2 wiring: the code-mode proxy command tools
(execute_command) must route to the project override so the raw
framework diagnostic never leaks, and when no project module is
importable the framework generic text stays unchanged (non-UwUChat
deployments unaffected).
"""

from __future__ import annotations

import os
from unittest.mock import patch

from langchain_core.messages import AIMessage

from airunner_services.llm.managers.mixins.generation_response_support import (
    _tool_only_fallback,
    fallback_response_for_empty_result,
)


def _execute_command_turn() -> dict:
    """Return a result dict whose final AIMessage calls execute_command
    with empty content and records it as executed (the runtime shape —
    the workflow manager records executed tools in additional_kwargs)."""
    ai_msg = AIMessage(
        content="",
        tool_calls=[],
        additional_kwargs={"executed_tools": ["execute_command"]},
    )
    ai_msg.tool_calls = [{"name": "execute_command", "args": {}}]
    return {"messages": [ai_msg]}


def test_execute_command_routes_to_project_override() -> None:
    """With the UwUChat override importable, execute_command gets the
    code-mode line — never the raw diagnostic."""
    result = _tool_only_fallback(["execute_command"])
    assert "I tried to run that" in result
    assert "execute_command" not in result
    assert "non-mutating" not in result.lower()


def test_execute_command_empty_result_uses_override() -> None:
    """fallback_response_for_empty_result with execute_command tool_calls
    returns the project override, not the raw diagnostic."""
    result = fallback_response_for_empty_result(_execute_command_turn(), [])
    assert "I tried to run that" in result
    assert "attempted a tool-based response" not in result


def test_execute_command_without_project_uses_framework_generic() -> None:
    """Without an importable project module, execute_command falls back
    to the framework generic text (non-UwUChat deployments unchanged)."""
    old_project = os.environ.get("AIRUNNER_PROJECT")
    os.environ["AIRUNNER_PROJECT"] = ""
    try:
        with patch(
            "airunner_services.llm.managers.mixins."
            "generation_response_support._try_project_fallback",
            return_value="",
        ):
            result = _tool_only_fallback(["execute_command"])
    finally:
        if old_project is None:
            os.environ.pop("AIRUNNER_PROJECT", None)
        else:
            os.environ["AIRUNNER_PROJECT"] = old_project
    assert "non-mutating" in result.lower()
    assert "execute_command" in result


def test_read_only_code_tool_routes_to_override() -> None:
    """list_registered_projects (added to READ_ONLY_TASK_TOOLS) routes
    to the project override too."""
    result = _tool_only_fallback(["list_registered_projects"])
    assert "I tried to run that" in result
    assert "list_registered_projects" not in result
