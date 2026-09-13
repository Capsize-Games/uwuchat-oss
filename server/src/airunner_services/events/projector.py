"""Pure-function projection helpers for event replay."""

from __future__ import annotations

from typing import Any


def project_state(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reconstruct the conversation message list by replaying *events*.

    This is a pure function with no database access. It applies each
    event's mutation to an in-memory message list and returns the
    final state.

    Returns:
        List of message dicts representing the projected conversation.
    """
    messages: list[dict[str, Any]] = []

    for event in events:
        ev_type = event.get("event_type", "")
        payload = event.get("payload") or {}

        if ev_type == "message_append":
            if payload.get("role") in ("user", "assistant"):
                messages.append({
                    "role": payload["role"],
                    "content": payload.get("content", ""),
                    "thinking_content": payload.get("thinking_content"),
                    "metadata_type": payload.get("metadata_type"),
                })
        elif ev_type == "message_delete":
            idx = payload.get("visible_index")
            if isinstance(idx, int) and 0 <= idx <= len(messages):
                messages = messages[:idx]
        elif ev_type == "conversation_truncate":
            keep = payload.get("keep_count")
            if isinstance(keep, int) and 0 <= keep <= len(messages):
                messages = messages[:keep]

    return messages
