"""Tool-event stashing helpers for ToolExecutionMixin.

Tool results are emitted during tool execution, BEFORE the final
narration is persisted.  These helpers buffer each completed event on
the owner's message history so the assistant message dict can carry
``tool_events`` (the same shape the client's live ``tool_status`` frames
accumulate) — letting reloaded threads render the tool widgets with real
status/details.  Never propagate failures.
"""

from __future__ import annotations

from typing import Any


def attach_tool_events(message_dict: dict, role: str, owner: Any) -> None:
    """Attach this turn's buffered tool events to assistant messages.

    The buffer is consumed on attach so it never leaks into the next
    turn.  Called by the message-build mixin when the narration is
    persisted.
    """
    if role != "assistant":
        return
    pending = getattr(owner, "_pending_tool_events", None)
    if not pending:
        return
    message_dict["tool_events"] = list(pending)
    owner._pending_tool_events = None


def stash_tool_event(
    owner: Any,
    tool_id: str,
    tool_name: str,
    query: str,
    details: str | None,
    status: str = "completed",
) -> None:
    """Buffer one tool result for the turn's assistant message.

    Mirrors the ``_pending_bot_mood`` pattern: the event is buffered on
    ``message_history._pending_tool_events`` and attached by
    ``DatabaseChatMessageBuildMixin`` when the narration is saved.
    ``status`` is ``"completed"`` or ``"error"`` so reloaded threads
    render the correct status dot.
    """
    try:
        _memory = getattr(owner, "_memory", None)
        if _memory is None:
            return
        msg_hist = getattr(_memory, "message_history", None)
        if msg_hist is None:
            return
        pending = getattr(msg_hist, "_pending_tool_events", None)
        if pending is None:
            pending = []
            msg_hist._pending_tool_events = pending
        position = getattr(owner, "_narration_length", 0)
        pending.append(
            {
                "tool_id": tool_id,
                "tool_name": tool_name,
                "status": status,
                "query": query,
                "details": details,
                "position": position,
            }
        )
    except Exception:
        pass
