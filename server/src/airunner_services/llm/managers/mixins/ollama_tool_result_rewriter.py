"""Rewrite tool results into readable prose for local Ollama daemons.

The local GGUF daemon (airunnerdesktop in ``AIRUNNER_OLLAMA_MODE``,
serving Qwen3.5-9B for UwUchat code-mode dialogue) does NOT render a
``role: "tool"`` message into the model's chat template.  The model
therefore never sees the result of its own tool call, so it re-issues
the same call forever (the "tool failed / blank line" loop).

Proven by direct eval against the daemon: feeding the tool result as
plain prose in a user-role message immediately makes the model advance
to the next tool call; every ``tool``-role variant is dropped.

This module rewrites ``ToolMessage`` objects into user-role prose for
the Ollama-compatible chat path only, so non-Ollama providers keep the
native tool-call protocol.  The rewrite is applied at prompt-build time
so the model's visible history is unchanged for other purposes.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)


def should_rewrite_tool_results(owner: Any) -> bool:
    """Return True when the current chat model is an Ollama daemon.

    The local code-mode dialogue model (Qwen3.5-9B via
    airunnerdesktop's Ollama-compat endpoint) cannot consume
    ``role: "tool"`` messages.  Detected via the chat model's base URL
    pointing at an Ollama-compatible daemon.

    LangChain's ``ChatOpenAI`` stores the endpoint on
    ``openai_api_base`` (not ``base_url``), so all the real attribute
    names are checked.  A ``bind_tools`` wrapper exposes the underlying
    model via ``_ModelBinding``/``.__fields__`` — fall back to walking
    ``model_kwargs`` and any ``openai_*`` attribute.
    """
    chat_model = getattr(owner, "_chat_model", None)
    if chat_model is None:
        return False
    base_url = ""
    for attr in (
        "openai_api_base",
        "openai_base_url",
        "base_url",
        "api_base",
    ):
        value = getattr(chat_model, attr, None)
        if value:
            base_url = str(value)
            break
    if not base_url:
        model_kwargs = getattr(chat_model, "model_kwargs", None) or {}
        base_url = str(model_kwargs.get("base_url") or "")
    # A bound ChatOpenAI hides the base under its own kwargs chain.
    if not base_url:
        root = getattr(chat_model, "_ModelBinding__inner", None) or getattr(
            chat_model, "inner", None
        )
        if root is not None:
            base_url = str(
                getattr(root, "openai_api_base", "") or ""
            )
    return "11434" in base_url or "11435" in base_url


def rewrite_tool_results_for_ollama(
    messages: list[BaseMessage],
) -> list[BaseMessage]:
    """Return *messages* in the shape the Ollama daemon can consume.

    Two transformations, both required for the local Qwen daemon:

    1. Each ``ToolMessage`` becomes a ``HumanMessage`` whose text names
       the tool that ran and quotes its result (the daemon drops
       ``role: "tool"``, but reads user prose).

    2. Each ``AIMessage`` whose ``tool_calls`` were materialized from
       Qwen's embedded JSON is converted BACK to the Qwen form: the
       tool call as ``{"tool_call": {...}}`` JSON in the content, with
       ``tool_calls`` cleared.  The daemon's Ollama shim cannot consume
       LangChain/OpenAI ``tool_calls`` in history — feeding them back
       makes the model produce a text reply instead of continuing.
    """
    rewritten: list[BaseMessage] = []
    for message in messages:
        if isinstance(message, ToolMessage):
            content = str(getattr(message, "content", "") or "")
            name = getattr(message, "name", None) or "tool"
            rewritten.append(
                HumanMessage(
                    content=f"Tool result ({name}): {content}",
                )
            )
            continue
        if isinstance(message, AIMessage):
            calls = getattr(message, "tool_calls", None) or []
            content = str(getattr(message, "content", "") or "")
            if calls and not content.strip():
                # Rebuild the Qwen JSON-as-content form the daemon emits.
                payloads = []
                for call in calls:
                    name = call.get("name", "?")
                    args = call.get("args") or {}
                    payloads.append(
                        '{"tool_call": {"name": ' + json.dumps(name)
                        + ', "arguments": ' + json.dumps(args) + "}}"
                    )
                if payloads:
                    rewritten.append(
                        AIMessage(content="\n".join(payloads), tool_calls=[]),
                    )
                    continue
        rewritten.append(message)
    return rewritten
