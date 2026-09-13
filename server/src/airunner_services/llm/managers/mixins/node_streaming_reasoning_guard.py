"""Per-call guard that reconciles thinking-mode reasoning with tool_choice.

DeepSeek rejects thinking mode when a restrictive tool_choice is bound
or when ToolMessages are present in the conversation history.  This
module strips the ``reasoning`` extra_body parameter in those cases so
DeepSeek calls don't fail with 400.

The workaround is DeepSeek-specific — Claude and other providers that
support the reasoning parameter do not need it stripped, and stripping
it may degrade response quality on tool-continuation turns.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


def _is_deepseek_model(chat_model: Any) -> bool:
    """Return True when the active model is DeepSeek."""
    name = (
        getattr(chat_model, "model", None)
        or getattr(chat_model, "model_name", None)
        or ""
    )
    if not isinstance(name, str):
        return False
    return name.startswith("deepseek/")


def has_restrictive_tool_choice(chat_model: Any) -> bool:
    """Return True when the bound model forces a specific tool_choice.

    A restrictive choice is anything other than ``None`` or ``"auto"`` —
    e.g. ``"any"``, ``"required"``, or a named-function dict.
    """
    binding_kwargs = getattr(chat_model, "kwargs", {}) or {}
    tool_choice = binding_kwargs.get("tool_choice")
    if tool_choice in (None, "auto"):
        return False
    return True


def has_tool_continuation(prompt: Any) -> bool:
    """Return True when the prompt contains a ToolMessage from a prior call.

    DeepSeek thinking mode fails with 400 when the conversation history
    includes ToolMessages (i.e. we are in the follow-up turn after the
    model previously called a tool).  The error message is still
    "Thinking mode does not support this tool_choice" even though no
    explicit tool_choice was set — DeepSeek applies an implicit constraint
    to tool-continuation turns.
    """
    try:
        from langchain_core.messages import ToolMessage

        messages = getattr(prompt, "messages", None)
        if messages is None:
            if isinstance(prompt, list):
                messages = prompt
            else:
                return False
        return any(isinstance(m, ToolMessage) for m in messages)
    except Exception:
        return False


def _remove_reasoning(kwargs: Dict, extra_body: Dict) -> Dict:
    """Return a copy of kwargs with the 'reasoning' key stripped."""
    new_extra_body = {
        key: value
        for key, value in extra_body.items()
        if key != "reasoning"
    }
    new_kwargs = dict(kwargs)
    if new_extra_body:
        new_kwargs["extra_body"] = new_extra_body
    else:
        new_kwargs.pop("extra_body", None)
    return new_kwargs


def strip_reasoning_for_forced_tool(
    chat_model: Any,
    kwargs: Dict,
    prompt: Optional[Any] = None,
) -> Dict:
    """Drop reasoning params when thinking mode would cause a 400 error.

    Two cases strip reasoning, both DeepSeek-specific:
    1. A restrictive tool_choice is bound — DeepSeek rejects thinking
       mode with any choice other than None/"auto".
    2. The prompt contains ToolMessages — DeepSeek applies an implicit
       restriction on thinking mode in tool-continuation turns
       regardless of whether an explicit tool_choice is set.

    For non-DeepSeek models (Claude, etc.) the reasoning parameter is
    preserved — stripping it may degrade response quality on
    tool-continuation turns without avoiding any known error.

    Returns the original mapping when no change is required, otherwise a
    new mapping with the ``reasoning`` entry removed from ``extra_body``.
    """
    extra_body = kwargs.get("extra_body")
    if not isinstance(extra_body, dict) or "reasoning" not in extra_body:
        return kwargs
    if not _is_deepseek_model(chat_model):
        return kwargs
    if has_restrictive_tool_choice(chat_model):
        return _remove_reasoning(kwargs, extra_body)
    if prompt is not None and has_tool_continuation(prompt):
        return _remove_reasoning(kwargs, extra_body)
    return kwargs
