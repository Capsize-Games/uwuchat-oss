"""Append-only event recorder for the conversation audit log."""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


def record(
    event_type: str,
    *,
    chatbot_id: int,
    actor: str,
    payload: dict[str, Any],
    conversation_id: int | None = None,
    session_id: int | None = None,
    actor_user_id: int | None = None,
    sequence_num: int | None = None,
) -> None:
    """Write one event to the audit log. Fire-and-forget; never raises."""
    try:
        from airunner_services.database.models.conversation_event import (
            ConversationEvent,
        )

        ConversationEvent.objects.create(
            event_type=event_type,
            chatbot_id=chatbot_id,
            actor=actor,
            payload=payload,
            conversation_id=conversation_id,
            session_id=session_id,
            actor_user_id=actor_user_id,
            sequence_num=sequence_num,
        )
    except Exception:
        _log.exception(
            "Failed to record event type=%s chatbot=%s",
            event_type,
            chatbot_id,
        )
