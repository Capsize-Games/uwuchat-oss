"""Mood update orchestration — per-turn and session-end entry points."""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_SKIP_TYPES = frozenset({
    "tool_calls", "tool_result", "rag_injection", "proactive_trigger",
})


# ── Message extraction ───────────────────────────────────────

def _is_display_message(msg: dict) -> bool:
    """True if *msg* is a user or assistant message (not metadata)."""
    if not isinstance(msg, dict):
        return False
    if msg.get("metadata_type") in _SKIP_TYPES:
        return False
    return msg.get("role") in ("user", "assistant")


def _all_session_messages(session_id: int) -> list[dict]:
    """Return all user/assistant messages from a session."""
    from airunner_services.database.models.conversation import (
        Conversation,
    )
    conversations = (
        Conversation.objects.query()
        .filter(Conversation.session_id == session_id)
        .order_by(Conversation.id.asc())
        .all()
    )
    all_msgs: list[dict] = []
    for conv in conversations:
        for msg in getattr(conv, "value", None) or []:
            if _is_display_message(msg):
                all_msgs.append(msg)
    return all_msgs


def _last_messages(session_id: int, n: int = 6) -> list[dict]:
    """Return the last *n* user/assistant messages from the session."""
    all_msgs = _all_session_messages(session_id)
    return all_msgs[-n:] if len(all_msgs) > n else all_msgs


# ── Mood helpers ─────────────────────────────────────────────

def _current_mood_from_obj(conversation) -> dict:
    """Return current mood dict from a Conversation ORM instance."""
    if conversation is None:
        return {}
    return (conversation.user_data or {}).get("current_mood") or {}


def _enrich_payload(result: dict) -> dict:
    """Add kaomoji to a parsed mood result."""
    from airunner_services.llm.tools.mood_tools import (
        _DEFAULT_KAOMOJI,
        _kaomoji_for_mood,
    )
    result["kaomoji"] = _kaomoji_for_mood(
        result.get("mood", "neutral"),
        result.get("kaomoji", _DEFAULT_KAOMOJI),
    )
    return result


# ── Parsing ──────────────────────────────────────────────────

def _parse_mood(raw: str) -> Optional[dict]:
    """Extract mood JSON from LLM response."""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(raw[start:end])
    except Exception:
        return None


# ── Pipeline ─────────────────────────────────────────────────

def _call_and_parse(
    context,
    is_session_end: bool,
    call_chain_id: str | None,
    chatbot_id: int | None,
) -> Optional[dict]:
    """Build prompt, call LLM, parse JSON; return mood dict or None."""
    from airunner_services.llm.mood.prompt import build_mood_prompt
    from airunner_services.llm.mood.llm_call import _call_llm

    prompt = build_mood_prompt(context, is_session_end=is_session_end)
    raw = _call_llm(
        prompt, call_chain_id=call_chain_id, chatbot_id=chatbot_id,
    )
    if not raw:
        return None
    return _parse_mood(raw)


def _compute_mood_payload(
    context,
    is_session_end: bool = False,
    call_chain_id: str | None = None,
    chatbot_id: int | None = None,
) -> Optional[dict]:
    """Run the mood-update pipeline, return enriched payload."""
    if not context.messages:
        return None
    result = _call_and_parse(
        context, is_session_end, call_chain_id, chatbot_id,
    )
    if result is None:
        return None
    return _enrich_payload(result)


def _build_context_for_turn(chatbot, conversation):
    """Assemble MoodContext for a per-turn mood update."""
    from airunner_services.llm.mood.context import (
        MoodContext,
        build_mood_context,
    )
    session_id = getattr(conversation, "session_id", None)
    if session_id is None:
        return MoodContext(chatbot_name="")
    messages = _last_messages(session_id, 6)
    mood_dict = _current_mood_from_obj(conversation)
    return build_mood_context(chatbot, conversation, messages, mood_dict)


# ── Public entry points ──────────────────────────────────────

def update_mood_sync(
    chatbot,
    conversation,
    call_chain_id: str | None = None,
) -> Optional[dict]:
    """Compute and persist an updated mood synchronously (per-turn)."""
    from airunner_services.llm.mood.persistence import _persist_mood

    context = _build_context_for_turn(chatbot, conversation)
    result = _compute_mood_payload(
        context, call_chain_id=call_chain_id,
        chatbot_id=getattr(chatbot, "id", None),
    )
    if result is None:
        return None
    conv_id = getattr(conversation, "id", None)
    if conv_id is None:
        return None
    _persist_mood(conv_id, result)
    return result


def _build_context_for_session(
    session_id: int,
    conversation_id: int,
    chatbot_id: int | None,
):
    """Fetch data and build MoodContext for session-end path."""
    from airunner_services.llm.mood.context import build_mood_context
    from airunner_services.llm.mood.persistence import (
        _get_chatbot,
        _get_conversation,
    )
    messages = _all_session_messages(session_id)
    if len(messages) < 2:
        return None
    chatbot = _get_chatbot(chatbot_id)
    conversation = _get_conversation(conversation_id)
    mood_dict = _current_mood_from_obj(conversation)
    return build_mood_context(chatbot, conversation, messages, mood_dict)


def _try_session_mood(
    session_id: int,
    conversation_id: int,
    chatbot_id: int | None,
) -> None:
    """Build context, compute mood, persist — or no-op if no data."""
    from airunner_services.llm.mood.persistence import _persist_mood

    context = _build_context_for_session(
        session_id, conversation_id, chatbot_id,
    )
    if context is None:
        return
    result = _compute_mood_payload(context, is_session_end=True)
    if result is None:
        return
    _persist_mood(conversation_id, result)


def update_mood_from_session(
    session_id: int,
    chatbot_name: str,
    conversation_id: int,
    chatbot_id: int | None = None,
) -> None:
    """Compute and persist mood from the full session arc."""
    from airunner_services.llm.pipeline_loader import is_enabled

    if not is_enabled("INTRA_SESSION_MOOD"):
        return
    if not session_id or not chatbot_name or not conversation_id:
        return
    try:
        _try_session_mood(session_id, conversation_id, chatbot_id)
    except Exception as exc:
        from airunner_services.llm.mood.persistence import (
            _log_session_end_failure,
        )
        _log_session_end_failure(exc)
