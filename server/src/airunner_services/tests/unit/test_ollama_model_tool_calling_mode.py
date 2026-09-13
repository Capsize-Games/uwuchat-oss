"""Tests that the Ollama-compatible chat model uses native tool calling.

Without ``tool_calling_mode = "native"`` the framework's
``_get_tool_calling_mode()`` defaults to ``"react"`` and the prompt
builder injects ReAct "Action:" text instructions, which fight
``ChatOllama``'s native ``bind_tools()`` path and leak raw ReAct text
into streamed responses. Same pattern as ``ReasoningAwareChatOpenAI``.
"""

from __future__ import annotations


def test_ollama_model_uses_native_tool_calling_mode() -> None:
    """The compat model instance carries tool_calling_mode = "native"."""
    from airunner_services.cloud.llm.model_builders import (
        _make_ollama_compatible_chat_model_cls,
    )

    cls = _make_ollama_compatible_chat_model_cls()
    model = cls(model="test", base_url="http://localhost:11434")

    assert model.tool_calling_mode == "native"
