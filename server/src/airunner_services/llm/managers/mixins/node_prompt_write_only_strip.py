"""Strip write-only tool call pairs from message history.

Temporary fix for DeepSeek thinking-mode 400 errors on tool-continuation
turns. Write-only tools fire and forget — their ToolMessage results carry
no data the model needs, so removing them keeps thinking mode active for
the follow-up response.

See wiki/planned_work/two-phase-tool-architecture.md for the planned
two-phase architecture that replaces this approach.
"""

from __future__ import annotations

from typing import List

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

# Tools whose results are never read back by the model (fire-and-forget).
# Adding a tool here causes its AIMessage+ToolMessage pair to be stripped
# from the prompt before the response-generation call.
_WRITE_ONLY_TOOLS = frozenset({
    "record_knowledge",
    "update_mood",
    "record_character_fact",
    "toggle_tts",
    "clear_conversation",
})


def _tool_name(tc) -> str:
    """Extract the name from a tool call dict or ToolCall object."""
    if isinstance(tc, dict):
        return tc.get("name", "") or ""
    return getattr(tc, "name", "") or ""


def _tool_call_id(tc) -> str:
    """Extract the ID from a tool call dict or ToolCall object."""
    if isinstance(tc, dict):
        return tc.get("id", "") or ""
    return getattr(tc, "id", "") or ""


def _all_write_only(tool_calls: list) -> bool:
    """Return True when every call in tool_calls targets a write-only tool."""
    if not tool_calls:
        return False
    return all(_tool_name(tc) in _WRITE_ONLY_TOOLS for tc in tool_calls)


def _strip_ai_tool_calls(msg: AIMessage) -> AIMessage:
    """Return a copy of an AIMessage with tool_calls removed."""
    return AIMessage(
        content=msg.content,
        additional_kwargs=msg.additional_kwargs or {},
    )


def _write_only_call_ids(messages: List[BaseMessage]) -> set:
    """Collect tool_call IDs from AIMessages that only call write-only tools."""
    ids: set = set()
    for msg in messages:
        if not isinstance(msg, AIMessage):
            continue
        tool_calls = getattr(msg, "tool_calls", None) or []
        if _all_write_only(tool_calls):
            for tc in tool_calls:
                tc_id = _tool_call_id(tc)
                if tc_id:
                    ids.add(tc_id)
    return ids


def _strip_write_only_tool_pairs(
    messages: List[BaseMessage],
) -> List[BaseMessage]:
    """Remove AIMessage+ToolMessage pairs where ALL calls are write-only.

    Strips the tool_calls from each qualifying AIMessage and drops the
    corresponding ToolMessages, leaving the AIMessage content (which may
    include a brief acknowledgement from the model) in the history.

    Returns the original list unchanged when no ToolMessages are present
    or when no write-only pairs are found.
    """
    if not any(isinstance(m, ToolMessage) for m in messages):
        return messages
    strip_ids = _write_only_call_ids(messages)
    if not strip_ids:
        return messages
    result: List[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            tool_calls = getattr(msg, "tool_calls", None) or []
            if _all_write_only(tool_calls):
                result.append(_strip_ai_tool_calls(msg))
                continue
        elif isinstance(msg, ToolMessage):
            if getattr(msg, "tool_call_id", None) in strip_ids:
                continue
        result.append(msg)
    return result
