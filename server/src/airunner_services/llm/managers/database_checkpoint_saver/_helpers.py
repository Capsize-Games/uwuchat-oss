"""Pure helpers for the database checkpoint saver package."""

from __future__ import annotations

import uuid
from collections import OrderedDict
from typing import Any

_CHECKPOINT_STATE_MAX_SIZE = 100


def _fresh_config() -> dict:
    """Return a stateless/fresh run config with random IDs.

    Used by ``put()`` in stateless mode and when no conversation is
    available, so each call starts from a brand-new thread/checkpoint.
    """
    return {
        "configurable": {
            "thread_id": str(uuid.uuid4()),
            "checkpoint_id": str(uuid.uuid4()),
        }
    }


def _checkpoint_id_from(checkpoint: dict) -> str:
    """Return the checkpoint's id, generating a fresh UUID when absent."""
    checkpoint_id = checkpoint.get("id")
    if not checkpoint_id:
        checkpoint_id = str(uuid.uuid4())
    return checkpoint_id


def _db_visible_message_count(db_value: list) -> int:
    """Count DB messages that represent visible conversation turns.

    Proactive/interjection messages are appended to Conversation.value by
    a background thread that bypasses the checkpointer, so tool-call and
    tool-result entries are excluded from the count.
    """
    return sum(
        1 for m in db_value
        if m.get("role") in ("user", "assistant", "bot")
        and m.get("metadata_type") not in ("tool_calls", "tool_result")
    )


def _diag_message_summary(messages: list) -> list:
    """Return a compact (type, content-length) summary for diagnostics."""
    return [
        (type(m).__name__, len(str(getattr(m, "content", "") or "")))
        for m in messages
    ]


def _store_checkpoint_state(
    state: OrderedDict[str, Any],
    thread_id: str,
    checkpoint: dict,
    metadata: dict,
    messages: list,
    logger: Any,
) -> None:
    """Store a checkpoint in the per-instance LRU cache.

    Evicts the oldest entry when the cache exceeds its max size.  Keyed
    by thread_id (str(conversation_id)) so different conversations never
    contaminate each other.
    """
    state[thread_id] = {
        "checkpoint": checkpoint,
        "metadata": metadata,
        "messages": messages,
    }
    state.move_to_end(thread_id)
    if len(state) > _CHECKPOINT_STATE_MAX_SIZE:
        state.popitem(last=False)
    logger.debug(
        "Stored full checkpoint state with %d messages for thread %s",
        len(messages),
        thread_id,
    )


def _copy_with_trimmed(
    checkpoint: dict, original: list, trimmed: list
) -> dict:
    """Return a shallow-copied checkpoint whose messages are *trimmed*.

    Returns the original checkpoint unchanged when trimming did not
    modify the list (identity check), matching the caller's expectation
    that no copy is made on the common no-trim path.
    """
    if trimmed is original:
        return checkpoint
    data = dict(checkpoint)
    data["channel_values"] = dict(data.get("channel_values", {}))
    data["channel_values"]["messages"] = trimmed
    return data


def _build_checkpoint(messages: list) -> dict:
    """Build the LangGraph checkpoint dict for *messages*."""
    return {
        "v": 1,
        "id": str(uuid.uuid4()),
        "ts": "",
        "channel_values": {
            "messages": messages,
        },
        "channel_versions": {},
        "versions_seen": {},
        "updated_channels": None,
    }


def _build_metadata(messages: list) -> dict:
    """Build the LangGraph checkpoint metadata for *messages*."""
    return {
        "source": "update",
        "step": len(messages),
        "parents": {},
    }
