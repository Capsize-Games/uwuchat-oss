"""Unit tests for Qwen embedded tool-call materialization.

The local Qwen3.5-9B daemon emits tool calls as JSON inside the message
content (``{"tool_call": {"name", "arguments"}}``) instead of an OpenAI
``tool_calls`` array.  These tests verify that the framework
materializes those embedded calls into real LangChain ``tool_calls`` so
the agentic loop routes to the tools node instead of narrating the JSON.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage

from airunner_services.llm.managers.mixins.embedded_tool_calls import (
    materialize_embedded_tool_calls,
)

_QWEN_READ = (
    '{"tool_call": {"name": "read_file", "arguments": '
    '{"project_name": "airunner", '
    '"path": "plans/parallel-tasks/w16-continue2.md"}}}'
)


def test_materializes_qwen_embedded_tool_call() -> None:
    """A content-only message with Qwen JSON yields real tool_calls."""
    msg = AIMessage(content=_QWEN_READ, tool_calls=[])
    out = materialize_embedded_tool_calls(msg)
    assert out.tool_calls, "expected materialized tool_calls"
    call = out.tool_calls[0]
    assert call["name"] == "read_file"
    assert call["args"] == {
        "project_name": "airunner",
        "path": "plans/parallel-tasks/w16-continue2.md",
    }
    assert call["type"] == "tool_call"
    # The embedded JSON is stripped from the content.
    assert out.content == ""


def test_native_tool_calls_win() -> None:
    """A message with real tool_calls is never overridden."""
    native = [{
        "name": "execute_command",
        "args": {"project_name": "airunner", "command": "pwd"},
        "id": "call_1",
        "type": "tool_call",
    }]
    msg = AIMessage(content="prose", tool_calls=native)
    out = materialize_embedded_tool_calls(msg)
    assert out.tool_calls == native
    assert out.content == "prose"


def test_plain_text_unchanged() -> None:
    """Ordinary text with no embedded JSON passes through untouched."""
    msg = AIMessage(content="I'll check the files now.", tool_calls=[])
    out = materialize_embedded_tool_calls(msg)
    assert out.tool_calls == []
    assert out.content == "I'll check the files now."


def test_empty_content_unchanged() -> None:
    """An empty message is left alone (no false tool_calls)."""
    msg = AIMessage(content="", tool_calls=[])
    out = materialize_embedded_tool_calls(msg)
    assert out.tool_calls == []
    assert out.content == ""


def test_malformed_embedded_json_unchanged() -> None:
    """Broken JSON in content must not fabricate a tool call."""
    bad = '{"tool_call": {"name": "read_file", "arguments": {'
    msg = AIMessage(content=bad, tool_calls=[])
    out = materialize_embedded_tool_calls(msg)
    assert out.tool_calls == []
    assert out.content == bad


def test_materializes_fenced_json_block() -> None:
    """The daemon wraps tool calls in ```json ... ``` fences."""
    content = (
        '```json\n'
        '{"tool_call": {"name": "execute_command", "arguments": '
        '{"project_name": "airunner", "command": "ls -la"}}}\n'
        '```'
    )
    out = materialize_embedded_tool_calls(
        AIMessage(content=content, tool_calls=[]),
    )
    assert out.tool_calls
    assert out.tool_calls[0]["name"] == "execute_command"
    assert out.tool_calls[0]["args"] == {
        "project_name": "airunner", "command": "ls -la",
    }


def test_materializes_nested_bare_json() -> None:
    """A bare object with nested braces (arguments dict) still parses."""
    content = (
        '{"tool_call": {"name": "read_file", "arguments": '
        '{"project_name": "airunner", "path": "plans/a.md"}}}'
    )
    out = materialize_embedded_tool_calls(
        AIMessage(content=content, tool_calls=[]),
    )
    assert out.tool_calls
    assert out.tool_calls[0]["name"] == "read_file"
    assert out.tool_calls[0]["args"]["path"] == "plans/a.md"


def test_materializes_called_tool_narration() -> None:
    """The headlesscode-style narration (Called tool ... with arguments
    {python dict}) is materialized so the tool actually executes."""
    content = (
        '[Called tool "execute_command" with arguments '
        "{'command': 'grep -rn \"example-lan-password\" plans/', "
        "'cwd': None, 'timeout': 30}]"
    )
    out = materialize_embedded_tool_calls(
        AIMessage(content=content, tool_calls=[]),
    )
    assert out.tool_calls
    call = out.tool_calls[0]
    assert call["name"] == "execute_command"
    assert call["args"]["command"].startswith("grep -rn")
    assert call["args"]["cwd"] is None
    assert call["args"]["timeout"] == 30
    assert call["type"] == "tool_call"


def test_plain_narration_without_called_tool_unchanged() -> None:
    """Narration that merely mentions 'tool' stays a content reply."""
    content = "Let me call the tool to check the files."
    out = materialize_embedded_tool_calls(
        AIMessage(content=content, tool_calls=[]),
    )
    assert out.tool_calls == []
    assert out.content == content
