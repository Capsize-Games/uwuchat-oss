"""Semantic (pgvector) retrieval for per-turn bridge context.

Requires ConversationTurn.embedding to be populated by index_session_turns.
Degrades silently when embeddings are absent.

Date-anchored questions ("yesterday", "today", etc.) are skipped here and
must go through recall_conversation instead, which can filter and label by
actual calendar dates rather than treating date words as embedding fodder.
"""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.world.temporal_query import (
    _is_date_query,
)

logger = logging.getLogger(__name__)

_TURN_CHAR_LIMIT = 200
_SEMANTIC_LIMIT = 3


def _turn_text(raw) -> str:
    """Return turn content string (EncryptedText already decrypts on read)."""
    return str(raw) if raw else ""


def append_semantic_context(
    parts: list[str],
    chatbot_id: int,
    current_session_id: int,
    user_message: str,
    chatbot_name: str,
    owner: Any,
) -> None:
    """Append the 3 most semantically relevant past exchanges."""
    try:
        # Date-anchored questions must go through recall_conversation
        # (date-filtered + labeled), not blind topical similarity
        # search, which has no concept of "yesterday" vs "today".
        if _is_date_query(user_message):
            return

        from airunner_services.database.models.conversation_turn import (
            ConversationTurn,
        )
        from airunner_services.llm.managers.agent.pgvector_store import (
            embed_query,
        )

        embedding_model = getattr(owner, "_embedding_model", None)
        if embedding_model is None:
            embedding_model = getattr(owner, "embedding_model", None)
        if embedding_model is None:
            return

        query_vector = embed_query(embedding_model, user_message)
        distance = ConversationTurn.embedding.cosine_distance(
            list(query_vector),
        ).label("distance")

        user_rows = (
            ConversationTurn.objects.query(ConversationTurn, distance)
            .filter(
                ConversationTurn.chatbot_id == chatbot_id,
                ConversationTurn.session_id != current_session_id,
                ConversationTurn.role == "user",
                ConversationTurn.embedding.isnot(None),
            )
            .order_by(distance)
            .limit(_SEMANTIC_LIMIT)
            .all()
        )
        if not user_rows:
            return

        from airunner_services.llm.managers.prompt_builder import (
            per_turn_temporal,
        )

        exchange_count = 0
        for user_turn, _dist in user_rows:
            a_row = _paired_assistant(
                ConversationTurn,
                chatbot_id,
                user_turn.session_id,
                user_turn.turn_index,
            )
            u_when = per_turn_temporal.relative_time_ago(
                user_turn.created_at.isoformat()
            )
            u_text = _turn_text(user_turn.content or "")[:_TURN_CHAR_LIMIT]
            parts.append(f"({u_when}) User: {u_text}")
            if a_row:
                a_text = _turn_text(a_row.content or "")[:_TURN_CHAR_LIMIT]
                parts.append(f"{chatbot_name}: {a_text}")
            if exchange_count < len(user_rows) - 1:
                parts.append("")
            exchange_count += 1
    except Exception:
        pass


def _paired_assistant(model, chatbot_id: int,
                      session_id: int, turn_index: int):
    """Return the assistant turn immediately after the given user turn."""
    try:
        return (
            model.objects.query()
            .filter(
                model.chatbot_id == chatbot_id,
                model.session_id == session_id,
                model.turn_index == turn_index + 1,
                model.role == "assistant",
            )
            .first()
        )
    except Exception:
        return None
