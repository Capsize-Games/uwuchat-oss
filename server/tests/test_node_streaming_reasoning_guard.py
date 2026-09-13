"""Tests for node_streaming_reasoning_guard — model-gated reasoning strip.

These tests verify that the DeepSeek-specific reasoning-parameter stripping
in ``strip_reasoning_for_forced_tool`` is correctly gated to only apply when
the bound model is DeepSeek.  Claude and other providers must keep their
``reasoning`` extra_body key intact on tool-continuation and forced-tool
turns.

No live LLM API calls — all chat-model objects are plain mocks.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from airunner_services.llm.managers.mixins.node_streaming_reasoning_guard \
    import (
        _is_deepseek_model,
        has_restrictive_tool_choice,
        has_tool_continuation,
        strip_reasoning_for_forced_tool,
    )


# ── _is_deepseek_model ─────────────────────────────────────────────

@pytest.mark.parametrize(
    "model_attr,expected",
    [
        ("deepseek/deepseek-chat", True),
        ("deepseek/deepseek-v4-pro", True),
        ("anthropic/claude-haiku-4.5", False),
        ("anthropic/claude-sonnet-4.5", False),
        ("openai/gpt-4o", False),
        ("", False),
    ],
)
def test_is_deepseek_model(model_attr: str, expected: bool) -> None:
    """_is_deepseek_model returns True only for deepseek/ prefixes."""
    chat_model = MagicMock()
    chat_model.model = model_attr
    assert _is_deepseek_model(chat_model) == expected


def test_is_deepseek_model_falls_back_to_model_name() -> None:
    """model_name attribute is checked when model is absent."""
    chat_model = MagicMock()
    del chat_model.model
    chat_model.model_name = "deepseek/deepseek-chat"
    assert _is_deepseek_model(chat_model) is True


# ── has_restrictive_tool_choice ────────────────────────────────────

def test_has_restrictive_tool_choice_none() -> None:
    """None tool_choice is not restrictive."""
    chat_model = MagicMock()
    chat_model.kwargs = {"tool_choice": None}
    assert has_restrictive_tool_choice(chat_model) is False


def test_has_restrictive_tool_choice_auto() -> None:
    """"auto" tool_choice is not restrictive."""
    chat_model = MagicMock()
    chat_model.kwargs = {"tool_choice": "auto"}
    assert has_restrictive_tool_choice(chat_model) is False


def test_has_restrictive_tool_choice_any() -> None:
    """"any" tool_choice is restrictive."""
    chat_model = MagicMock()
    chat_model.kwargs = {"tool_choice": "any"}
    assert has_restrictive_tool_choice(chat_model) is True


def test_has_restrictive_tool_choice_named_function() -> None:
    """A named-function dict tool_choice is restrictive."""
    chat_model = MagicMock()
    chat_model.kwargs = {
        "tool_choice": {"type": "function", "function": {"name": "f"}}
    }
    assert has_restrictive_tool_choice(chat_model) is True


def test_has_restrictive_tool_choice_no_kwargs() -> None:
    """No kwargs at all is not restrictive."""
    chat_model = MagicMock()
    chat_model.kwargs = {}
    assert has_restrictive_tool_choice(chat_model) is False


# ── has_tool_continuation ──────────────────────────────────────────

def test_has_tool_continuation_no_tool_messages() -> None:
    """Plain HumanMessage/AIMessage prompt has no tool continuation."""
    from langchain_core.messages import HumanMessage

    prompt = MagicMock()
    prompt.messages = [HumanMessage(content="hello")]
    assert has_tool_continuation(prompt) is False


def test_has_tool_continuation_with_tool_message() -> None:
    """Prompt containing a ToolMessage is a tool continuation."""
    from langchain_core.messages import ToolMessage

    prompt = MagicMock()
    prompt.messages = [ToolMessage(content="result", tool_call_id="1")]
    assert has_tool_continuation(prompt) is True


def test_has_tool_continuation_list_prompt() -> None:
    """A plain list input containing a ToolMessage is detected."""
    from langchain_core.messages import ToolMessage

    msgs = [ToolMessage(content="result", tool_call_id="1")]
    assert has_tool_continuation(msgs) is True


def test_has_tool_continuation_no_messages() -> None:
    """A prompt object with no messages attr is not a continuation."""
    prompt = MagicMock(spec=[])
    assert has_tool_continuation(prompt) is False


# ── strip_reasoning_for_forced_tool — DeepSeek (strips) ────────────

def _deepseek_chat_model(tool_choice: Any = None) -> MagicMock:
    """Return a mocked DeepSeek chat model with the given tool_choice."""
    model = MagicMock()
    model.model = "deepseek/deepseek-chat"
    model.kwargs = {"tool_choice": tool_choice}
    return model


def _kwargs_with_reasoning() -> dict:
    """Return kwargs carrying an extra_body.reasoning entry."""
    return {
        "extra_body": {"reasoning": {"effort": "medium", "exclude": False}},
        "temperature": 0.7,
    }


def test_strip_deepseek_restrictive_tool_choice_strips() -> None:
    """DeepSeek with restrictive tool_choice strips reasoning."""
    model = _deepseek_chat_model(tool_choice="any")
    kwargs = _kwargs_with_reasoning()
    result = strip_reasoning_for_forced_tool(model, kwargs)
    assert "reasoning" not in result.get("extra_body", {})


def test_strip_deepseek_tool_continuation_strips() -> None:
    """DeepSeek with ToolMessages in history strips reasoning."""
    from langchain_core.messages import ToolMessage

    model = _deepseek_chat_model(tool_choice=None)
    kwargs = _kwargs_with_reasoning()
    prompt = MagicMock()
    prompt.messages = [ToolMessage(content="ok", tool_call_id="x")]
    result = strip_reasoning_for_forced_tool(model, kwargs, prompt)
    assert "reasoning" not in result.get("extra_body", {})


def test_strip_deepseek_no_restriction_keeps() -> None:
    """DeepSeek with auto tool_choice and no ToolMessages keeps reasoning."""
    model = _deepseek_chat_model(tool_choice="auto")
    kwargs = _kwargs_with_reasoning()
    result = strip_reasoning_for_forced_tool(model, kwargs)
    assert result is kwargs  # identity — no copy needed


# ── strip_reasoning_for_forced_tool — Claude (keeps) ───────────────

def _claude_chat_model(tool_choice: Any = None) -> MagicMock:
    """Return a mocked Claude chat model with the given tool_choice."""
    model = MagicMock()
    model.model = "anthropic/claude-haiku-4.5"
    model.kwargs = {"tool_choice": tool_choice}
    return model


def test_strip_claude_restrictive_tool_choice_keeps_reasoning() -> None:
    """Claude with restrictive tool_choice keeps reasoning — not DeepSeek."""
    model = _claude_chat_model(tool_choice="any")
    kwargs = _kwargs_with_reasoning()
    result = strip_reasoning_for_forced_tool(model, kwargs)
    assert result is kwargs  # identity — unchanged


def test_strip_claude_tool_continuation_keeps_reasoning() -> None:
    """Claude with ToolMessages keeps reasoning — not DeepSeek."""
    from langchain_core.messages import ToolMessage

    model = _claude_chat_model(tool_choice=None)
    kwargs = _kwargs_with_reasoning()
    prompt = MagicMock()
    prompt.messages = [ToolMessage(content="ok", tool_call_id="x")]
    result = strip_reasoning_for_forced_tool(model, kwargs, prompt)
    assert result is kwargs  # identity — unchanged


# ── strip_reasoning_for_forced_tool — no reasoning key ─────────────

def test_strip_no_extra_body_returns_unchanged() -> None:
    """No extra_body at all — pass through."""
    model = _deepseek_chat_model(tool_choice="any")
    kwargs = {"temperature": 0.7}
    result = strip_reasoning_for_forced_tool(model, kwargs)
    assert result is kwargs


def test_strip_extra_body_without_reasoning_returns_unchanged() -> None:
    """extra_body present but no reasoning key — pass through."""
    model = _deepseek_chat_model(tool_choice="any")
    kwargs = {"extra_body": {"custom": True}}
    result = strip_reasoning_for_forced_tool(model, kwargs)
    assert result is kwargs
