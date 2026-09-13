"""Persistence helpers for the mood-update pipeline.

Handles writing mood payloads to conversation.user_data and
associated error logging.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _get_chatbot(chatbot_id: int | None):
    """Fetch a Chatbot by id, returning None on failure."""
    if chatbot_id is None:
        return None
    try:
        from airunner_services.database.models.chatbot import Chatbot

        return Chatbot.objects.get(chatbot_id)
    except Exception:
        return None


def _get_conversation(conversation_id: int):
    """Fetch a Conversation by id, returning None on failure."""
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        return Conversation.objects.get(conversation_id)
    except Exception:
        return None


def _log_persist_failure(exc: Exception) -> None:
    """Log a mood-persist failure at the appropriate level."""
    from airunner_services.utils.network_retry import (
        is_transient_network_error,
        log_network_failure,
    )

    if is_transient_network_error(exc):
        log_network_failure(logger, "Mood persist failed", exc)
    else:
        logger.error("Mood persist failed", exc_info=True)


def _persist_mood(conversation_id: int, payload: dict) -> None:
    """Write mood payload to conversation.user_data."""
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        conv = Conversation.objects.get(conversation_id)
        if conv is None:
            return
        ud = conv.user_data or {}
        ud["current_mood"] = payload
        Conversation.objects.update(conversation_id, user_data=ud)
    except Exception as exc:
        _log_persist_failure(exc)


def _log_session_end_failure(exc: Exception) -> None:
    """Log a session-end mood failure at the appropriate level."""
    from airunner_services.utils.network_retry import (
        is_transient_network_error,
        log_network_failure,
    )

    if is_transient_network_error(exc):
        log_network_failure(
            logger, "Session-end mood update failed", exc
        )
    else:
        logger.error(
            "Session-end mood update failed", exc_info=True
        )
