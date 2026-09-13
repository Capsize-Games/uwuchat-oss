"""Cloud LLM model builders — create OpenRouter/Ollama/OpenAI models."""

from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel

_log = logging.getLogger(__name__)
_delta_logged = [False]


def _annotate_reasoning_chunk(gen: Any, choices: list) -> None:
    """Inject reasoning_content from a streaming delta into gen."""
    if not choices:
        return
    delta = choices[0].get("delta") or {}
    raw = delta.get("reasoning") or delta.get("reasoning_content")
    if not _delta_logged[0] and (delta.get("content") or raw):
        _delta_logged[0] = True
        _log.info(
            "[THINKING DEBUG] first content delta keys: %s  content_len=%d",
            list(delta.keys()),
            len(str(delta.get("content", ""))),
        )
    if raw is None or gen is None:
        return
    from langchain_core.messages import AIMessageChunk

    if isinstance(gen.message, AIMessageChunk):
        gen.message.additional_kwargs["reasoning_content"] = raw


def _build_reasoning_aware_class() -> type:
    """Return ChatOpenAI subclass that preserves reasoning_content."""
    from langchain_openai import ChatOpenAI

    class ReasoningAwareChatOpenAI(ChatOpenAI):
        tool_calling_mode: str = "native"

        def _convert_chunk_to_generation_chunk(
            self,
            chunk: dict,
            default_chunk_class: type,
            base_generation_info: Optional[dict],
        ):
            gen = super()._convert_chunk_to_generation_chunk(
                chunk, default_chunk_class, base_generation_info
            )
            _annotate_reasoning_chunk(gen, chunk.get("choices") or [])
            return gen

        def _get_request_payload(
            self,
            input_,
            *,
            stop: Optional[list[str]] = None,
            **kwargs: Any,
        ) -> dict:
            """Re-inject reasoning_content into assistant message dicts.

            DeepSeek requires reasoning_content to be round-tripped
            back when a tool-calling assistant message appears in
            conversation history.  LangChain's base serialization
            drops it — this override walks the serialized payload
            and restores reasoning_content from the original
            AIMessage's additional_kwargs.
            """
            payload = super()._get_request_payload(
                input_, stop=stop, **kwargs
            )
            from langchain_core.messages import AIMessage

            messages = payload.get("messages", [])
            input_messages = (
                list(input_) if isinstance(input_, list)
                else [input_]
            )
            for i, msg_dict in enumerate(messages):
                if i >= len(input_messages):
                    break
                src = input_messages[i]
                if not isinstance(src, AIMessage):
                    continue
                reasoning = (
                    src.additional_kwargs.get("reasoning_content")
                )
                if reasoning:
                    msg_dict["reasoning_content"] = reasoning
            return payload

    return ReasoningAwareChatOpenAI


def _provider_order_for_model(model_name: str) -> list[str]:
    """Return the pinned upstream provider order for one OpenRouter
    model.

    Pinning to a single instance (rather than letting OpenRouter
    auto-route) keeps consecutive requests in one conversation on the
    same backend — required for Anthropic-style prompt caching, since
    a cache written on one instance is invisible to a read on
    another, and generally avoids inconsistent behavior across
    providers mid-conversation.

    deepseek/* models pin to the native "deepseek" provider (2026-08-20,
    explicit user override — see DEEPSEEK_V4_FLASH_MODEL in
    conf/model_settings.py for why). Previously pinned to DeepInfra, a
    US-incorporated host chosen to satisfy the no-Chinese-hosted-
    inference policy in wiki/UwUChat-Pricing-and-Cost-Economics.md;
    DeepInfra started returning "no endpoints" for this account
    (account-side restriction, not a DeepInfra outage) so the pin was
    moved to DeepSeek's own China-hosted API instead. That trades away
    the US-host requirement — re-litigate before treating this as
    permanent.

    Everything else (Claude, Gemini) keeps the existing google-vertex
    pin — the only provider this account's OpenRouter data-policy
    settings (openrouter.ai/settings/privacy) allow for Claude, and
    Gemini's native host regardless.

    IMPORTANT — pricing: if a pinned provider's actual per-token rate
    differs from OpenRouter's blended default, *also* add an entry to
    ``PINNED_PROVIDER_PRICING`` in
    ``airunner_services.llm.openrouter_catalog`` so the catalog sync
    does not silently overwrite the corrected price on every run.
    """
    if model_name.startswith("deepseek/"):
        return ["deepseek"]
    return ["google-vertex"]


def create_openrouter_model(
    api_key: str,
    model_name: str,
    temperature: float = 0.7,
    max_tokens: int = 500,
) -> BaseChatModel:
    """Create one OpenRouter chat model."""
    from airunner_services.downloads.policy import (
        is_openrouter_allowed,
    )

    _raise_if_remote_disabled("OpenRouter", is_openrouter_allowed())
    cls = _build_reasoning_aware_class()
    model = cls(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=temperature,
        max_tokens=max_tokens,
        request_timeout=120,
        stream_options={"include_usage": True},
        # See _provider_order_for_model for why this is pinned per-
        # model rather than left to OpenRouter's auto-routing.
        extra_body={
            "provider": {
                "order": _provider_order_for_model(model_name),
                "allow_fallbacks": False,
            },
        },
    )
    # ChatOpenAI supports native function calling via bind_tools().
    # Without this attribute the workflow manager defaults to "react"
    # and injects ReAct-format text instructions that override the
    # native tool call mechanism, causing the model to output raw
    # "Action: / Action Input:" text instead of structured tool calls.
    # NOTE: tool_calling_mode is set as a class default on
    # ReasoningAwareChatOpenAI so no post-construction assignment needed.
    return model


def create_deepinfra_model(
    api_key: str,
    model_name: str,
    temperature: float = 0.7,
    max_tokens: int = 500,
) -> BaseChatModel:
    """Create one DeepInfra chat model via its OpenAI-compatible API."""
    from airunner_services.downloads.policy import (
        is_deepinfra_allowed,
    )

    _raise_if_remote_disabled("DeepInfra", is_deepinfra_allowed())
    cls = _build_reasoning_aware_class()
    model = cls(
        model=model_name,
        openai_api_key=api_key,
        openai_api_base="https://api.deepinfra.com/v1/openai",
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return model


def _make_ollama_compatible_chat_model_cls():
    """Return a ``ChatOllama`` subclass that tolerates call-time kwargs
    from the codebase's provider-agnostic call sites (e.g. reflection
    inference, response validation), which pass HuggingFace/OpenAI-style
    generation kwargs (``max_tokens``, ``do_sample``, ``temperature``,
    ...) intended for whichever chat model is currently active.
    ``ollama.Client.chat()`` accepts only a fixed set of top-level
    kwargs and raises ``TypeError`` on anything else — every sampling
    parameter belongs under ``options`` instead — so unrecognized
    kwargs are folded into ``options`` (or translated, for
    ``max_tokens`` -> ``num_predict``) before reaching the client,
    rather than requiring every call site to know Ollama's shape.
    """
    from langchain_ollama import ChatOllama

    # The only top-level kwargs ollama.Client.chat() itself accepts;
    # everything else belongs under "options". Kept in sync with
    # ChatOllama._chat_params's own param assembly.
    _TOP_LEVEL_KEYS = frozenset(
        {"messages", "stream", "model", "reasoning", "format",
         "options", "keep_alive", "tools"}
    )
    _RENAMES = {"max_tokens": "num_predict"}

    class _OllamaCompatChatModel(ChatOllama):
        # Native tool calling: without this, _get_tool_calling_mode()
        # defaults to "react" and the prompt builder injects ReAct
        # "Action:" text instructions that fight ChatOllama's native
        # bind_tools() support, making the model emit raw ReAct text
        # (surfaced to the user as "Action: …" leaks) instead of
        # structured tool calls. Same pattern as
        # ReasoningAwareChatOpenAI above.
        tool_calling_mode: str = "native"

        @property
        def enable_thinking(self) -> bool:
            """Alias for ``reasoning`` (Ollama's ``think`` request field).

            ``_apply_request_thinking_override`` toggles
            ``enable_thinking`` on the active chat model for every
            other provider; without this alias the per-request
            thinking toggle silently no-ops for Ollama (``ChatOllama``
            has no such attribute), and Qwen3-family "thinking" models
            default to emitting their full chain-of-thought as the
            only visible stream content, starving the actual answer of
            the tail of ``max_tokens``.
            """
            return bool(self.reasoning)

        @enable_thinking.setter
        def enable_thinking(self, value: bool) -> None:
            self.reasoning = bool(value)

        def _chat_params(self, messages, stop=None, **kwargs):
            options = dict(kwargs.pop("options", None) or {})
            for key in [k for k in kwargs if k not in _TOP_LEVEL_KEYS]:
                value = kwargs.pop(key)
                target = _RENAMES.get(key)
                if target is not None:
                    options.setdefault(target, value)
                elif key != "do_sample":
                    # do_sample has no Ollama equivalent — sampling is
                    # always on. Everything else Ollama might
                    # recognize (temperature, top_p, seed, ...) goes
                    # into options.
                    options.setdefault(key, value)
            if options:
                kwargs["options"] = options
            return super()._chat_params(messages, stop=stop, **kwargs)

        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            """Generate a chat result, clearing tool-call message content.

            The local code-daemon's ollama-compat layer fills a
            tool-call message's ``content`` with a raw framework
            diagnostic string ("The model attempted a tool-based
            response...").  A tool-call message must never carry
            narration text — the model speaks AFTER the tool result.
            Clearing the content at the source keeps it out of the
            message, out of conversation history, and out of the
            model's own context on subsequent calls (which otherwise
            parrots the diagnostic as its final reply).
            """
            result = super()._generate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
            for generation in getattr(result, "generations", []):
                message = getattr(generation, "message", None)
                if message is None:
                    continue
                tool_calls = getattr(message, "tool_calls", None)
                if tool_calls:
                    message.content = ""
            return result

    return _OllamaCompatChatModel


def create_ollama_model(
    model_name: str,
    base_url: str = "http://localhost:11434",
    temperature: float = 0.7,
) -> BaseChatModel:
    """Create one Ollama chat model."""
    try:
        chat_model_cls = _make_ollama_compatible_chat_model_cls()

        return chat_model_cls(
            model=model_name,
            base_url=base_url,
            temperature=temperature,
        )
    except ImportError as error:
        raise ImportError(
            "langchain-ollama is required for Ollama support. "
            "Install with: pip install langchain-ollama"
        ) from error


def create_openai_model(
    api_key: str,
    model_name: str = "gpt-4",
    temperature: float = 0.7,
    max_tokens: int = 500,
) -> BaseChatModel:
    """Create one OpenAI chat model."""
    from airunner_services.downloads.policy import (
        is_openai_allowed,
    )

    _raise_if_remote_disabled("OpenAI", is_openai_allowed())
    chat_openai = _require_chat_openai()
    return chat_openai(
        model=model_name,
        openai_api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------


def _require_chat_openai() -> type:
    """Return the ChatOpenAI class or raise an installation error."""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as error:
        raise ImportError(
            "langchain-openai is required for OpenAI/OpenRouter "
            "support. Install with: pip install langchain-openai"
        ) from error
    return ChatOpenAI


def _raise_if_remote_disabled(service_name: str, allowed: bool) -> None:
    """Raise when a remote model provider is disabled in settings."""
    if allowed:
        return
    raise ValueError(
        f"{service_name} is disabled in privacy settings. Enable it "
        "in Preferences -> Privacy & Security -> External Services."
    )
