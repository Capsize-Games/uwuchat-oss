"""Tests that stream_model_response preserves the model's native mode.

``NodeResponseGenerationHelper.stream_model_response`` used to force
``tool_calling_mode = "react"`` on every call, which broke the final
synthesis call for native tool-calling models (``ReasoningAwareChatOpenAI``
and ``_OllamaCompatChatModel`` both declare ``tool_calling_mode =
"native"``).  The mode must be left untouched — the default ``"react"``
when the attribute is absent keeps legacy behavior.
"""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from airunner_services.llm.managers.mixins import (
    node_response_generation_helper,
)


def _ollama_compat_model():
    """Build one _OllamaCompatChatModel instance."""
    from airunner_services.cloud.llm.model_builders import (
        _make_ollama_compatible_chat_model_cls,
    )
    cls = _make_ollama_compatible_chat_model_cls()
    return cls(model="test", base_url="http://localhost:11434")


def _reasoning_aware_model():
    """Build one ReasoningAwareChatOpenAI instance."""
    from airunner_services.cloud.llm.model_builders import (
        _build_reasoning_aware_class,
    )
    cls = _build_reasoning_aware_class()
    return cls(
        model="test",
        openai_api_key="sk-test",
        openai_api_base="http://localhost:1",
        max_tokens=10,
        request_timeout=5,
    )


def _stream_once(chat_model) -> None:
    """Run stream_model_response once against a stubbed owner."""
    streaming_stub = SimpleNamespace(
        generate_streaming_response=lambda prompt, kwargs: AIMessage(
            content="done",
            tool_calls=[],
        )
    )
    owner = SimpleNamespace(
        _chat_model=chat_model,
        _get_streaming_response_helper=lambda: streaming_stub,
    )
    helper = node_response_generation_helper.NodeResponseGenerationHelper(
        owner
    )
    helper.stream_model_response([HumanMessage(content="hi")], {})


def test_ollama_compat_model_keeps_native_mode() -> None:
    """_OllamaCompatChatModel stays native after stream_model_response."""
    model = _ollama_compat_model()
    assert model.tool_calling_mode == "native"
    _stream_once(model)
    assert model.tool_calling_mode == "native"


def test_reasoning_aware_model_keeps_native_mode() -> None:
    """ReasoningAwareChatOpenAI stays native after stream_model_response."""
    model = _reasoning_aware_model()
    assert model.tool_calling_mode == "native"
    _stream_once(model)
    assert model.tool_calling_mode == "native"
