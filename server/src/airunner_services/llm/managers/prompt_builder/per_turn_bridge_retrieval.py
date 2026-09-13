"""Cross-session retrieval for per-turn bridge context.

Provides two context signals injected into every conversational turn:
1. Tail context — last 3 exchanges from the previous session, verbatim.
2. Semantic retrieval — pgvector similarity search over all past turns.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_TURN_CHAR_LIMIT = 200
_TAIL_LIMIT = 2
_SEMANTIC_LIMIT = 3


def get_current_session_id(owner) -> Optional[int]:
    """Return the current session id from the owner, or None.

    First tries direct attribute probes, then resolves via the workflow
    manager's conversation record (the standard path for the LLM manager
    that passes owner._workflow_manager._conversation_id)."""
    for attr in ("chat_session_id", "session_id"):
        sid = getattr(owner, attr, None)
        if sid is not None:
            return int(sid)
    chat_session = getattr(owner, "chat_session", None)
    if chat_session is not None:
        sid = getattr(chat_session, "id", None)
        if sid is not None:
            return int(sid)
    # Standard path: LLM manager → _workflow_manager._conversation_id
    # → Conversation.session_id
    wm = getattr(owner, "_workflow_manager", None)
    conv_id = getattr(owner, "_conversation_id", None) or (
        getattr(wm, "_conversation_id", None) if wm else None
    )
    if conv_id is None:
        return None
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )
        conv = Conversation.objects.get(conv_id)
        if conv is not None:
            sid = getattr(conv, "session_id", None)
            if sid is not None:
                logger.debug(
                    "[BRIDGE] resolved session_id=%s from conv_id=%s",
                    sid,
                    conv_id,
                )
                return int(sid)
        logger.warning(
            "[BRIDGE] conv_id=%s found but session_id is None", conv_id
        )
    except Exception as exc:
        logger.warning("[BRIDGE] get_current_session_id failed: %s", exc)
    return None


def get_latest_user_message(owner) -> Optional[str]:
    """Return the most recent user message text from the owner state.

    Tries common attribute names; returns None if none found."""
    for attr in (
        "_current_prompt",
        "user_message",
        "_user_message",
        "current_user_message",
    ):
        msg = getattr(owner, attr, None)
        if msg:
            return str(msg)
    return None


def append_prior_tail(
    parts: list[str],
    chatbot_id: int,
    current_session_id: int,
    chatbot_name: str,
    current_conv_id: Optional[int] = None,
    user_message: str = "",
) -> None:
    """Append last exchanges from the most recent prior conversation.

    Reads directly from Conversation.value so no background indexing
    job is required — the data is always present.

    Skips entirely when ``user_message`` is a date-anchored question
    ("yesterday", "last week", etc.) — this block's date label can be
    empty (e.g. the prior conversation has no session_id) or simply
    wrong for the user's question, and unlike recall_conversation /
    search_conversations it has no real date filtering. Date-anchored
    questions must go through those tools instead.
    """
    if user_message:
        from airunner_services.world.temporal_query import _is_date_query
        if _is_date_query(user_message):
            return
    try:
        # Primary: find by prior session_id.
        prior_conv = _find_prior_conv_by_session(
            chatbot_id, current_session_id
        )
        # Fallback: find by conversation id < current.
        if prior_conv is None and current_conv_id:
            prior_conv = _find_prior_conv_by_id(
                chatbot_id, current_conv_id
            )
        if prior_conv is None:
            logger.debug(
                "[BRIDGE] no prior conversation found for chatbot_id=%s",
                chatbot_id,
            )
            return

        messages = getattr(prior_conv, "value", None) or []
        visible = [
            m for m in messages
            if isinstance(m, dict)
            and m.get("role") in ("user", "assistant")
            and m.get("content")
            and m.get("metadata_type") != "proactive_trigger"
        ]
        tail = visible[-_TAIL_LIMIT:]
        if not tail:
            return
        user_facts = [
            str(m.get("content", ""))[:_TURN_CHAR_LIMIT]
            for m in tail if m.get("role") == "user"
        ]
        if user_facts:
            when = _resolve_prior_tail_when(prior_conv)
            prefix = f"[from {when}] " if when else ""
            parts.append(prefix + "; ".join(user_facts))
        logger.debug(
            "[BRIDGE] injected %d tail turns from conv %s",
            len(tail),
            prior_conv.id,
        )
    except Exception as exc:
        logger.warning("[BRIDGE] append_prior_tail failed: %s", exc)


def _resolve_prior_tail_when(prior_conv) -> str:
    """Return a relative-time label for the prior conversation's last
    message, or empty string if unavailable."""
    try:
        from airunner_services.database.models.chat_session import (
            ChatSession,
        )
        from airunner_services.llm.managers.prompt_builder import (
            per_turn_temporal,
        )

        session_id = getattr(prior_conv, "session_id", None)
        if session_id is not None:
            sess = ChatSession.objects.get(session_id)
            if sess is not None and sess.last_message_at:
                return per_turn_temporal.relative_time_ago(
                    sess.last_message_at.isoformat()
                )
        # No session_id (legacy/orphaned conversation row) — fall back
        # to the conversation's own updated_at as an approximate label
        # rather than silently omitting any time signal at all.
        updated_at = getattr(prior_conv, "updated_at", None)
        if updated_at:
            return per_turn_temporal.relative_time_ago(
                updated_at.isoformat()
            )
        return ""
    except Exception:
        return ""


def _find_prior_conv_by_session(chatbot_id: int, current_session_id: int):
    """Return the most recent conversation in the nearest prior session."""
    try:
        from airunner_services.database.models.chat_session import (
            ChatSession,
        )
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        prior_session = (
            ChatSession.objects.query()
            .filter(
                ChatSession.chatbot_id == chatbot_id,
                ChatSession.id != current_session_id,
            )
            .order_by(ChatSession.id.desc())
            .first()
        )
        if prior_session is None:
            return None
        return (
            Conversation.objects.query()
            .filter(
                Conversation.session_id == prior_session.id,
            )
            .order_by(Conversation.id.desc())
            .first()
        )
    except Exception:
        return None


def _find_prior_conv_by_id(chatbot_id: int, current_conv_id: int):
    """Return the most recent conversation before current_conv_id."""
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        return (
            Conversation.objects.query()
            .filter(
                Conversation.chatbot_id == chatbot_id,
                Conversation.id < current_conv_id,
            )
            .order_by(Conversation.id.desc())
            .first()
        )
    except Exception:
        return None
