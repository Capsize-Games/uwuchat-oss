"""Mood computation, client emission, and persistence helpers.

Extracted from ``generation_execution_support``.  Computes a fresh
intra-session mood before the prompt is built, pushes it to the
WebSocket client, and persists it to the conversation's ``user_data``.
"""

from __future__ import annotations

from typing import Optional

from airunner_services.llm.managers.mixins.generation_execution_support._scheduling import (
    _resolve_conversation_id,
)


def _update_and_emit_mood(
    owner, call_chain_id: str | None = None
) -> Optional[dict]:
    """Compute and persist a fresh mood, returning the payload for
    client emission.  Call BEFORE setup_generation_workflow so the
    LLM receives the current mood in its per-turn context."""
    from airunner_services.llm.pipeline_loader import (
        is_enabled,
        pipeline_config,
    )

    if not is_enabled("INTRA_SESSION_MOOD"):
        return None
    interval = int(
        pipeline_config("INTRA_SESSION_MOOD").get("interval_turns", 5)
    )
    if interval <= 0:
        return None
    chatbot = getattr(owner, "chatbot", None)
    name = getattr(chatbot, "botname", "") if chatbot else ""
    if not name:
        return None
    wm = getattr(owner, "_workflow_manager", None)
    conv_id = getattr(wm, "_conversation_id", None) if wm else None
    if not conv_id:
        return None
    from airunner_services.database.models.conversation import (
        Conversation,
    )

    conv = Conversation.objects.get(conv_id)
    session_id = getattr(conv, "session_id", None) if conv else None
    if not session_id:
        return None
    from airunner_services.llm.rolling_compressor import (
        _count_assistant_turns,
    )

    turn_count = _count_assistant_turns(session_id)
    # Seed an initial mood on the very first turn (turn_count == 0),
    # then gate on interval thereafter.
    if turn_count > 0 and turn_count % interval != 0:
        owner.logger.info(
            "[MOOD GATE] skipped — turn_count=%d interval=%d "
            "session_id=%s",
            turn_count, interval, session_id,
        )
        return None
    owner.logger.info(
        "[MOOD GATE] computing — turn_count=%d interval=%d "
        "session_id=%s",
        turn_count, interval, session_id,
    )
    from airunner_services.llm.mood import update_mood_sync

    return update_mood_sync(
        chatbot, conv,
        call_chain_id=call_chain_id,
    )


def _emit_mood_to_client(owner, payload: Optional[dict]) -> None:
    """Push the mood payload to the WebSocket client."""
    if payload is None:
        return
    event_sink = getattr(owner, "_event_sink", None)
    if event_sink is None:
        return
    # Attach the current request_id so the mediator can route the
    # LLM_TEXT_STREAMED_SIGNAL mood message to the correct WebSocket
    # response queue.  Without it the signal is silently dropped.
    request_id = getattr(owner, "_current_request_id", None)
    if request_id:
        payload = dict(payload)
        payload["request_id"] = request_id
    try:
        event_sink.emit_bot_mood(payload)
    except Exception:
        pass


def _persist_auto_mood(owner, mood_payload: dict) -> None:
    """Persist auto-computed mood to conv.user_data so it survives reload.

    Called from do_generate when the intra-session mood engine produces
    a fresh mood.  This path is independent of the update_mood tool
    (which persists via _persist_mood_to_conversation in mood_tools.py)
    and the _attach_mood path (which runs after the stream yield and
    only fires when update_mood was called as a tool this turn).
    """
    conversation_id = _resolve_conversation_id(owner)
    logger = getattr(owner, "logger", None)
    if logger:
        logger.warning(
            "[MOOD DEBUG] _persist_auto_mood conv_id=%s mood=%r kaomoji=%r",
            conversation_id,
            mood_payload.get("mood") if mood_payload else None,
            mood_payload.get("kaomoji") if mood_payload else None,
        )
    if conversation_id is None:
        return
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )
        conv = Conversation.objects.get(conversation_id)
        if conv is None:
            if logger:
                logger.warning(
                    "[MOOD DEBUG] _persist_auto_mood conv NOT FOUND id=%s",
                    conversation_id,
                )
            return
        ud = conv.user_data or {}
        ud["current_mood"] = {
            "mood": mood_payload.get("mood", "neutral"),
            "emoji": mood_payload.get("emoji", "😐"),
            "kaomoji": mood_payload.get(
                "kaomoji", "(｡◕ᴗ◕｡)"
            ),
        }
        Conversation.objects.update(conversation_id, user_data=ud)
        if logger:
            logger.warning(
                "[MOOD DEBUG] _persist_auto_mood SUCCESS conv_id=%s",
                conversation_id,
            )
    except Exception as exc:
        if logger:
            logger.exception(
                "[MOOD DEBUG] _persist_auto_mood FAILED: %s", exc,
            )
