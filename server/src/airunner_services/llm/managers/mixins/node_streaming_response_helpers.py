"""Standalone helpers for NodeStreamingResponseHelper."""

from __future__ import annotations

from typing import Optional

from airunner_services.llm.managers.mixins.node_streaming_state import (
    StreamingState,
)
from airunner_services.llm.utils.stream_debug import print_stream_debug


# ---------------------------------------------------------------------------
# Tool-call markup filtering
# ---------------------------------------------------------------------------

_DEEPSEEK_TOOL_MARKERS = ("</｜", "<｜", "DSML", "tool_calls>")


def is_tool_call_start(text: str) -> bool:
    """Return True if text begins a ReAct or DeepSeek tool call block."""
    stripped = text.lstrip()
    if stripped.startswith("Action:") or stripped.startswith("Action Input:"):
        return True
    return "<｜tool" in text or "<|tool" in text


def is_tool_call_end(text: str) -> bool:
    """Return True if text closes an open tool call block."""
    return (
        "<｜tool▁calls▁end｜>" in text
        or "tool_calls>" in text
        or "DSML" in text
    )


def has_deepseek_tool_token(text: str) -> bool:
    """Return True if text contains a standalone DeepSeek tool token."""
    return any(m in text for m in _DEEPSEEK_TOOL_MARKERS)


def set_request_max_tokens(
    chat_model, requested: Optional[int]
) -> Optional[int]:
    """Temporarily set max_tokens on the chat model, returning old value."""
    if not requested:
        return None
    bound = getattr(chat_model, "bound", None)
    if bound is not None and hasattr(bound, "max_tokens"):
        chat_model = bound
    if not hasattr(chat_model, "max_tokens"):
        return None
    try:
        old = chat_model.max_tokens
        chat_model.max_tokens = requested
        return old
    except (ValueError, AttributeError):
        return None


def restore_max_tokens(chat_model, original: Optional[int]) -> None:
    """Restore the chat model's original max_tokens value."""
    if original is None:
        return
    bound = getattr(chat_model, "bound", None)
    if bound is not None and hasattr(bound, "max_tokens"):
        chat_model = bound
    try:
        chat_model.max_tokens = original
    except (ValueError, AttributeError):
        pass


def accumulate_chunk(state: StreamingState, chunk_message) -> None:
    """Merge one chunk into the accumulated message via LangChain's + op."""
    chunk_tool_calls = getattr(chunk_message, "tool_calls", None)
    try:
        if state.accumulated_message is None:
            state.accumulated_message = chunk_message
        else:
            state.accumulated_message = (
                state.accumulated_message + chunk_message
            )
    except Exception:
        if chunk_tool_calls:
            state.collected_tool_calls.extend(chunk_tool_calls)


def filter_tool_markup(state: StreamingState, text: str) -> str:
    """Suppress tool call markup that leaked into streamed text.

    Catches DeepSeek special tokens and ReAct Action/Action Input lines.
    Stateful — uses state.in_tool_call_tag across chunks.
    """
    if state.in_tool_call_tag:
        if is_tool_call_end(text):
            state.in_tool_call_tag = False
        return ""
    if is_tool_call_start(text):
        state.in_tool_call_tag = True
        return ""
    if has_deepseek_tool_token(text):
        return ""
    return text

_STRIP_ROLE_PREFIXES = (
    "assistant\n",
    "assistant:",
    "assistant ",
    "user\n",
    "user:",
    "user ",
    "human\n",
    "human:",
    "human ",
)
_STRIP_ROLE_EXACT = {
    "assistant",
    "assistant:",
    "user",
    "user:",
    "human",
    "human:",
}


def strip_leading_assistant_preamble(text: str) -> str:
    """Strip role labels from the start of one text chunk."""
    normalized = text.lstrip()
    lowered = normalized.lower()
    for prefix in _STRIP_ROLE_PREFIXES:
        if lowered.startswith(prefix):
            return normalized[len(prefix) :]
    if lowered in _STRIP_ROLE_EXACT:
        return ""
    return text


def _track_narration_length(owner, text_to_stream: str) -> None:
    """Track the cumulative visible narration length on the owner so tool
    status stashing can stamp each event with its inline position
    (persisted to the assistant message for reload)."""
    owner._narration_length = getattr(owner, "_narration_length", 0) + len(
        text_to_stream
    )


def _fix_digit_boundary_space(
    state: StreamingState, text_to_stream: str
) -> str:
    """Fix the byte-level BPE digit-boundary space artifact.

    The tokenizer emits sub-word tokens each with a leading space marker
    (digits become '1', ' 2', ' 3' → naive concat renders "1 2 3"
    instead of "123").  Drop the redundant boundary space ONLY when the
    next token is itself a space-prefixed DIGIT following a bare
    single-digit sub-word ('1' + ' 2' → '12').  A digit followed by a
    WORD keeps its space ("4 occurrences" must never become
    "4occurrences").
    """
    if (
        state.streamed_content
        and text_to_stream.startswith(" ")
        and len(text_to_stream) > 1
        and text_to_stream[1].isdigit()
        and len(state.streamed_content[-1]) == 1
        and state.streamed_content[-1].isdigit()
    ):
        return text_to_stream[1:]
    return text_to_stream


def store_visible_text(
    state: StreamingState,
    owner,
    request_id: Optional[str],
    text_to_stream: str,
    *,
    forward_to_callback: bool = True,
) -> None:
    """Persist one visible chunk and optionally forward it."""
    if not state.has_streamed_content:
        text_to_stream = strip_leading_assistant_preamble(text_to_stream)
    if not text_to_stream:
        return
    text_to_stream = _fix_digit_boundary_space(state, text_to_stream)
    state.streamed_content.append(text_to_stream)
    state.has_streamed_content = True
    _track_narration_length(owner, text_to_stream)
    if not forward_to_callback or not owner._token_callback:
        return
    print_stream_debug(
        "node_functions.visible",
        request_id=request_id,
        content=text_to_stream,
    )
    try:
        owner._token_callback(text_to_stream)
        # Flag that this model call streamed visible content —
        # used by _call_model to decide whether a stream-reset
        # is needed when the turn also produced tool calls.
        owner._streamed_content = True
    except Exception as callback_error:
        owner.logger.error(
            "Token callback failed: %s",
            callback_error,
            exc_info=True,
        )
