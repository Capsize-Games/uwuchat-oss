"""Append a headlesscode session card entry to a conversation.

Phase 5 of plans/uwuchat-headlesscode-live-session-integration.md: the
client renders any ``Message`` whose ``headlesscode_session_id`` is
set as a collapsible session card. The launch Celery task calls
:func:`append_session_card_entry` after ``/api/session/start`` returns
a real session id, so the card appears in the chat thread keyed by
that id.

The entry is a ``metadata_type: "headlesscode_session"`` message dict
in ``Conversation.value``. ``SessionManager.load_thread`` passes it
through to the client (its type is not in the thread's skip set) and
``DatabaseChatMessageHistory._is_metadata_entry`` filters it from the
LLM's context on future turns. The card entry carries no chat
``session_id`` — that field is reserved for the chat-session concept
and is stamped separately by ``load_thread``.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _card_entry(
    session_id: str,
    status: str,
    project_name: str,
    task_description: str,
    mode: str | None,
) -> dict[str, Any]:
    """Build the card entry dict for one launched session."""
    return {
        "role": "assistant",
        "name": "Headlesscode Session",
        "content": "",
        "timestamp": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "metadata_type": "headlesscode_session",
        "headlesscode_session_id": session_id,
        "status": status,
        "project_name": project_name,
        "task_description": task_description,
        "mode": mode,
    }


def append_session_card_entry(
    conversation_id: int | None,
    session_id: str,
    status: str,
    project_name: str,
    task_description: str,
    mode: str | None,
) -> None:
    """Append a session-card entry to *conversation_id*, never raising.

    No-op when *conversation_id* is None (the conversation could not
    be resolved at launch time). A failed append only costs the inline
    card — the session row is already persisted at that point, and the
    entry is re-creatable from that row.
    """
    if conversation_id is None:
        return
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        conv = Conversation.objects.get(conversation_id)
        if conv is None:
            return
        raw = getattr(conv, "value", None)
        if not isinstance(raw, list):
            logger.warning(
                "Headlesscode card: conversation %s value is not a "
                "list — skipping card append",
                conversation_id,
            )
            return
        value = list(raw)
        value.append(_card_entry(
            session_id, status, project_name, task_description, mode,
        ))
        Conversation.objects.update(conversation_id, value=value)
    except Exception:
        logger.warning(
            "Headlesscode card: could not append card entry for "
            "conversation %s",
            conversation_id,
            exc_info=True,
        )
