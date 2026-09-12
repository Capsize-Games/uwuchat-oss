"""Port of headlesscode's chat-thread event grouping (chat-thread.ts).

``group_events_into_chat`` reimplements the dashboard's
``groupEventsIntoChat`` (headlesscode's ``src/dashboard/chat-thread.ts``)
in pure Python: the flat chronological event feed served by
``GET /api/session/:id/events`` is grouped into conversation "turns"
(assistant bubble + inline tool calls + results) and system markers,
so the client can render a live session as a chat thread instead of a
flat log.

``chat_block_kinds`` maps that grouping onto the
``headlesscode_session_events.chat_block_kind`` column
(``turn``/``system``). The port is deliberately faithful — including
the default fallthrough that keeps unknown event types as system
markers — so behavior can be verified against headlesscode's own
``chat-thread.test.ts`` fixtures.
"""

from __future__ import annotations

from typing import Any

# Event types that close the current turn and render as inline system
# markers between turns (mirrors chat-thread.ts's grouped cases).
_TERMINAL_SYSTEM_TYPES = frozenset({
    "session_end",
    "llm_error",
    "checkpoint_saved",
    "paused",
    "resumed",
})

# Event types that belong to the current turn when one is open (and
# become lone system markers when the feed starts mid-session).
_TURN_CONTENT_TYPES = frozenset({
    "llm_response",
    "tool_call",
    "decision_answered",
    "llm_stream_chunk",
})

# Event types that START a fresh turn; the event itself is the turn's
# ``turnStart`` boundary marker.
_TURN_START_TYPES = frozenset({"iteration_start", "decision_blocked"})


def _task_from_session_start(event: dict[str, Any]) -> str:
    """Return the user's task text from a session_start event ("" when
    absent)."""
    task = event.get("task")
    return task if isinstance(task, str) else ""


def _push_system(state: dict[str, Any], event: dict[str, Any]) -> None:
    """Append a system marker block for *event*."""
    state["blocks"].append({"kind": "system", "event": event})


def _close_turn(state: dict[str, Any]) -> None:
    """Close the open turn (if any) into a turn block."""
    current = state["current"]
    if current is None:
        return
    block = {
        "kind": "turn",
        "turnStart": current["turnStart"],
        "events": current["events"],
    }
    if current["iteration"] is not None:
        block["iteration"] = current["iteration"]
    state["blocks"].append(block)
    state["current"] = None


def _handle_session_start(
    event: dict[str, Any], state: dict[str, Any],
) -> None:
    """Record the user's task; session_start is itself a system marker."""
    state["task"] = _task_from_session_start(event)
    _push_system(state, event)


def _handle_turn_start(
    event: dict[str, Any], state: dict[str, Any],
) -> None:
    """A fresh iteration/question starts a fresh assistant turn."""
    _close_turn(state)
    state["current"] = {
        "iteration": event.get("iteration"),
        "turnStart": event,
        "events": [],
    }


def _handle_tool_result(
    event: dict[str, Any], state: dict[str, Any],
) -> None:
    """Attach a tool_result to its preceding tool_call in the turn."""
    current = state["current"]
    if current is not None and current["events"]:
        last = current["events"][-1]
        if last.get("type") == "tool_call":
            current["events"].append(event)
            return
    _push_system(state, event)


def _handle_terminal(
    event: dict[str, Any], state: dict[str, Any],
) -> None:
    """Close the turn; the terminal event is an inline system marker."""
    _close_turn(state)
    _push_system(state, event)


def _handle_turn_content(
    event: dict[str, Any], state: dict[str, Any],
) -> None:
    """Belong to the current turn when there is one."""
    current = state["current"]
    if current is not None:
        current["events"].append(event)
    else:
        _push_system(state, event)


def _handle_unknown(
    event: dict[str, Any], state: dict[str, Any],
) -> None:
    """Unknown type: keep it as a system marker rather than hiding it."""
    _close_turn(state)
    _push_system(state, event)


def group_events_into_chat(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Group a flat event feed into chat blocks, mirroring
    ``groupEventsIntoChat``.

    Returns ``{"task": str, "blocks": [...]}``; ``task`` is present
    only when the feed carries a ``session_start`` event with task
    text. Blocks are ``{"kind": "turn", "iteration", "turnStart",
    "events"}`` or ``{"kind": "system", "event"}`` in feed order.
    """
    state: dict[str, Any] = {"task": "", "current": None, "blocks": []}
    for event in events:
        etype = event.get("type")
        if etype in _TURN_START_TYPES:
            _handle_turn_start(event, state)
        elif etype in _TERMINAL_SYSTEM_TYPES:
            _handle_terminal(event, state)
        elif etype in _TURN_CONTENT_TYPES:
            _handle_turn_content(event, state)
        elif etype == "session_start":
            _handle_session_start(event, state)
        elif etype == "tool_result":
            _handle_tool_result(event, state)
        else:
            _handle_unknown(event, state)
    _close_turn(state)
    result: dict[str, Any] = {"blocks": state["blocks"]}
    if state["task"]:
        result["task"] = state["task"]
    return result


def chat_block_kinds(events: list[dict[str, Any]]) -> list[str]:
    """Return one ``chat_block_kind`` ("turn"/"system") per input event.

    Events are matched to their block by object identity — the blocks
    returned by ``group_events_into_chat`` reference the same event
    dicts passed in — so the result is parallel to *events*. Unknown
    events default to "system".
    """
    grouping = group_events_into_chat(events)
    kinds_by_id: dict[int, str] = {}
    for block in grouping["blocks"]:
        if block["kind"] == "system":
            kinds_by_id[id(block["event"])] = "system"
        else:
            kinds_by_id[id(block["turnStart"])] = "turn"
            for event in block["events"]:
                kinds_by_id[id(event)] = "turn"
    return [kinds_by_id.get(id(event), "system") for event in events]


__all__ = ["chat_block_kinds", "group_events_into_chat"]
