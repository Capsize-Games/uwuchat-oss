"""Unit tests for the Ollama tool-result rewriter.

The local Qwen3.5-9B daemon drops ``role: "tool"`` messages, so the
model never sees its tool results and re-issues the same call forever.
The rewriter renders ToolMessages as readable user-role prose for the
Ollama-compatible chat path — the form proven (by direct eval against
the daemon) to make the model advance to the next tool call.
"""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from airunner_services.llm.managers.mixins.ollama_tool_result_rewriter import (
    rewrite_tool_results_for_ollama,
    should_rewrite_tool_results,
)


def _ollama_owner() -> SimpleNamespace:
    """Return an owner whose chat model points at an Ollama daemon."""
    model = SimpleNamespace(base_url="http://127.0.0.1:11434/v1")
    return SimpleNamespace(_chat_model=model)


def _cloud_owner() -> SimpleNamespace:
    """Return an owner whose chat model points at OpenRouter."""
    model = SimpleNamespace(base_url="https://openrouter.ai/api/v1")
    return SimpleNamespace(_chat_model=model)


def test_should_rewrite_true_for_ollama_daemon() -> None:
    """A base URL containing the Ollama port triggers the rewrite."""
    assert should_rewrite_tool_results(_ollama_owner()) is True


def test_should_rewrite_false_for_cloud() -> None:
    """OpenRouter keeps the native tool-call protocol."""
    assert should_rewrite_tool_results(_cloud_owner()) is False


def test_should_rewrite_false_without_model() -> None:
    """No chat model means no rewrite."""
    assert should_rewrite_tool_results(SimpleNamespace(_chat_model=None)) is False


def test_tool_message_becomes_user_prose() -> None:
    """A ToolMessage becomes a HumanMessage naming the tool + result."""
    msgs = [
        ToolMessage(
            content="File: plans/parallel-tasks/w16-continue2.md ...",
            tool_call_id="t1",
            name="read_file",
        ),
    ]
    out = rewrite_tool_results_for_ollama(msgs)
    assert len(out) == 1
    assert isinstance(out[0], HumanMessage)
    assert out[0].content.startswith("Tool result (read_file): File:")
    assert "w16-continue2.md" in out[0].content


def test_non_tool_messages_kept() -> None:
    """System, Human, and AIMessages pass through untouched."""
    msgs = [
        SystemMessage(content="sys"),
        HumanMessage(content="hi"),
        AIMessage(content="", tool_calls=[]),
        ToolMessage(content="data", tool_call_id="t1", name="list_files"),
    ]
    out = rewrite_tool_results_for_ollama(msgs)
    assert len(out) == 4
    assert isinstance(out[0], SystemMessage)
    assert isinstance(out[1], HumanMessage)
    assert isinstance(out[2], AIMessage)
    assert isinstance(out[3], HumanMessage)
    assert out[1].content == "hi"


def test_materialized_tool_calls_rewritten_to_qwen_json() -> None:
    """A materialized AIMessage tool_call becomes Qwen JSON content so
    the daemon's history (which cannot consume LangChain tool_calls)
    continues the loop."""
    from langchain_core.messages import ToolMessage

    msgs = [
        AIMessage(
            content="",
            tool_calls=[{
                "name": "read_file",
                "args": {
                    "project_name": "airunner",
                    "path": "plans/a.md",
                },
                "id": "tc1",
                "type": "tool_call",
            }],
        ),
        ToolMessage(
            content="File contents", tool_call_id="tc1", name="read_file",
        ),
    ]
    out = rewrite_tool_results_for_ollama(msgs)
    assert len(out) == 2
    ai = out[0]
    assert isinstance(ai, AIMessage)
    assert ai.tool_calls == []
    assert '"tool_call"' in ai.content
    assert '"name": "read_file"' in ai.content
    assert '"path": "plans/a.md"' in ai.content
    assert isinstance(out[1], HumanMessage)
    assert out[1].content.startswith("Tool result (read_file):")
