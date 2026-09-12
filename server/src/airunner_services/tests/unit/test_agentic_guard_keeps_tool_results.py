"""Tests that the agentic guard keeps tool results for the final call.

Covers the code-mode dead-end fix: ``force_final_response`` must pass
the full message list — tool-call AIMessages AND their ToolMessages —
to the final synthesis call, so the model can answer from the tool
output instead of producing nothing and triggering the generic
apology.  When the stream still yields no text, the project fallback
hook is tried before the framework's ``_IN_CHARACTER_FALLBACK``.
"""

from __future__ import annotations

import sys
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)

from airunner_services.llm.managers.mixins.node_agentic_guard import (
    _IN_CHARACTER_FALLBACK,
    NodeAgenticGuard,
)

_GH_TURN = [
    HumanMessage(
        content="use gh and list the open issues on github for the "
        "airunner repo"
    ),
    AIMessage(
        content="",
        tool_calls=[{
            "name": "list_registered_projects",
            "args": {},
            "id": "call_1",
        }],
    ),
    ToolMessage(
        content="registered projects: airunner, uwuchat",
        tool_call_id="call_1",
    ),
    AIMessage(
        content="",
        tool_calls=[{
            "name": "execute_command",
            "args": {"command": "gh issue list"},
            "id": "call_2",
        }],
    ),
    ToolMessage(
        content="issue #1: framework agentic guard strips tool results",
        tool_call_id="call_2",
    ),
]


class _FakeLogger:
    """No-op logger stub for guard tests."""

    def info(self, *args, **kwargs) -> None:
        """No-op info log."""

    def error(self, *args, **kwargs) -> None:
        """No-op error log."""

    def warning(self, *args, **kwargs) -> None:
        """No-op warning log."""


class _FakeOwner:
    """Minimal owner stub capturing the final synthesis call."""

    def __init__(self) -> None:
        """Create a stub with a default model reply."""
        self.logger = _FakeLogger()
        self.response: AIMessage | None = AIMessage(
            content="The airunner repo has 1 open issue.",
            tool_calls=[],
        )
        self.raise_exc: Exception | None = None
        self.last_prompt: list[BaseMessage] = []
        self.last_kwargs: dict[str, Any] = {}

    def _stream_model_response(
        self,
        prompt: list[BaseMessage],
        generation_kwargs: dict[str, Any],
    ) -> AIMessage | None:
        """Record the prompt and return the configured reply."""
        self.last_prompt = list(prompt)
        self.last_kwargs = dict(generation_kwargs)
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response


def _prompt_text(prompt: list[BaseMessage]) -> str:
    """Join the text content of one prompt message list."""
    return "\n".join(
        str(getattr(msg, "content", "") or "") for msg in prompt
    )


def test_force_final_prompt_keeps_tool_results_and_stop_instruction() -> None:
    """The final prompt keeps ToolMessage content plus the stop
    instruction — nothing is stripped from the full history."""
    owner = _FakeOwner()
    guard = NodeAgenticGuard(owner)
    result = guard.force_final_response(_GH_TURN, {"max_tokens": 100})

    assert len(owner.last_prompt) == len(_GH_TURN)
    prompt_text = _prompt_text(owner.last_prompt)
    assert "registered projects: airunner, uwuchat" in prompt_text
    assert (
        "issue #1: framework agentic guard strips tool results"
        in prompt_text
    )
    assert "Do not call any more tools" in prompt_text
    assert "called tools 6 times" in prompt_text
    assert result["messages"][0].content == owner.response.content


def test_force_final_returns_model_text_not_fallback() -> None:
    """A non-empty streamed reply is returned, never the apology."""
    owner = _FakeOwner()
    guard = NodeAgenticGuard(owner)
    result = guard.force_final_response(_GH_TURN, {})
    content = result["messages"][0].content
    assert content == "The airunner repo has 1 open issue."
    assert "I'm sorry" not in content
    assert result["workflow_continuation"] is False
    assert result["loop_count"] == 0


def test_force_final_falls_back_when_stream_none(monkeypatch) -> None:
    """A None stream uses the framework fallback when no project hook
    provides a line (non-UwUchat deployments)."""
    owner = _FakeOwner()
    owner.response = None
    guard = NodeAgenticGuard(owner)
    monkeypatch.setattr(
        NodeAgenticGuard, "_project_fallback", lambda self, messages: ""
    )
    result = guard.force_final_response(_GH_TURN, {})
    assert result["messages"][0].content == _IN_CHARACTER_FALLBACK


def test_force_final_uses_project_fallback_line(monkeypatch) -> None:
    """When the project hook returns a line, it replaces the apology."""
    owner = _FakeOwner()
    owner.response = None
    guard = NodeAgenticGuard(owner)
    monkeypatch.setattr(
        NodeAgenticGuard,
        "_project_fallback",
        lambda self, messages: (
            "I tried to run that on the project but it didn't go through."
        ),
    )
    result = guard.force_final_response(_GH_TURN, {})
    content = result["messages"][0].content
    assert "I tried to run that" in content
    assert content != _IN_CHARACTER_FALLBACK


def test_force_final_falls_back_when_stream_raises(monkeypatch) -> None:
    """A failing final call still lands on the project fallback."""
    owner = _FakeOwner()
    owner.raise_exc = RuntimeError("model exploded")
    guard = NodeAgenticGuard(owner)
    monkeypatch.setattr(
        NodeAgenticGuard, "_project_fallback", lambda self, messages: ""
    )
    result = guard.force_final_response(_GH_TURN, {})
    assert result["messages"][0].content == _IN_CHARACTER_FALLBACK


def test_project_fallback_returns_uwuchat_line(monkeypatch) -> None:
    """The real guarded import returns the code-mode line for
    execute_command when AIRUNNER_PROJECT is uwuchat."""
    monkeypatch.setenv("AIRUNNER_PROJECT", "uwuchat")
    guard = NodeAgenticGuard(_FakeOwner())
    line = guard._project_fallback(_GH_TURN)
    assert "I tried to run that" in line
    assert "execute_command" not in line


def test_project_fallback_empty_when_module_unimportable(monkeypatch) -> None:
    """An unimportable project module yields the empty framework line."""
    monkeypatch.setenv("AIRUNNER_PROJECT", "uwuchat")
    monkeypatch.setitem(
        sys.modules, "projects.uwuchat.server.fallback_response", None
    )
    guard = NodeAgenticGuard(_FakeOwner())
    assert guard._project_fallback(_GH_TURN) == ""
