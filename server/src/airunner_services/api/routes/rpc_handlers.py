"""RPC handlers for the unified /api/v1/events WebSocket.

Conversation handlers: rpc_conversation_handlers.py
Character handlers:    rpc_character_handlers.py
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)

if TYPE_CHECKING:
    from airunner_services.database.models.conversation import Conversation

logger = logging.getLogger(__name__)


def _latest_conversation_for(chatbot_id: int) -> Optional[Conversation]:
    """Return the most recent Conversation for a chatbot (any session)."""
    from airunner_services.database.models.conversation import Conversation

    return (
        Conversation.objects.query()
        .filter(Conversation.chatbot_id == chatbot_id)
        .order_by(Conversation.id.desc())
        .first()
    )


@_rpc_register("GET", "/api/v1/llm/uwu-session")
async def _rpc_uwu_session(body: dict, **kw: Any) -> dict[str, Any]:
    """Get or create the active session for a chatbot."""
    try:
        from airunner_services.llm.session_manager import (
            SessionManager,
        )
        from airunner_services.database.models.chatbot import Chatbot

        chatbot_id = body.get("chatbot_id")
        user_id = body.get("user_id")
        if not chatbot_id:
            return {"status": 400, "body": {"error": "chatbot_id required"}}
        chatbot = Chatbot.objects.get(int(chatbot_id))
        if not chatbot or getattr(chatbot, "deleted", False):
            return {
                "status": 404,
                "body": {"error": f"Chatbot {chatbot_id} not found"},
            }
        manager = SessionManager()
        session, conv, _cold_id, _gap_hours = manager.get_or_create_session(
            int(chatbot_id),
            int(user_id) if user_id else None,
        )
        # A fresh session has no linked Conversation yet (created on first
        # send); bind the UI to the most recent one the user is viewing.
        if conv is None:
            conv = _latest_conversation_for(int(chatbot_id))
        return {
            "status": 200,
            "body": {
                "conversation_id": getattr(conv, "id", None),
                "session_id": getattr(session, "id", None),
            },
        }
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="uwu-session error",
        )


@_rpc_register("POST", "/api/v1/llm/uwu-greeting")
async def _rpc_persist_uwu_greeting(body: dict, **kw: Any) -> dict[str, Any]:
    """Persist the opening greeting for a brand-new UwU chatbot.

    Creates a ``Conversation`` row with the greeting so it survives
    browser reloads.  Idempotent — calling this more than once for the
    same chatbot is a safe no-op (see SessionManager.persist_greeting).
    """
    try:
        from airunner_services.llm.session_manager import SessionManager
        from airunner_services.database.models.chatbot import Chatbot

        chatbot_id = body.get("chatbot_id")
        greeting = body.get("greeting")
        if not chatbot_id or not greeting:
            return {
                "status": 400,
                "body": {"error": "chatbot_id and greeting required"},
            }
        chatbot = Chatbot.objects.get(int(chatbot_id))
        if not chatbot or getattr(chatbot, "deleted", False):
            return {
                "status": 404,
                "body": {"error": f"Chatbot {chatbot_id} not found"},
            }
        manager = SessionManager()
        manager.persist_greeting(int(chatbot_id), greeting)
        return {"status": 200, "body": {"ok": True}}
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="uwu-greeting error",
        )


@_rpc_register("GET", "/api/v1/llm/thread")
async def _rpc_thread(body: dict, **kw: Any) -> dict[str, Any]:
    """Load the full persistent thread for a chatbot across all sessions."""
    try:
        from airunner_services.llm.session_manager import SessionManager
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        chatbot_id = body.get("chatbot_id")
        if not chatbot_id:
            return {"status": 400, "body": {"error": "chatbot_id required"}}
        limit = int(body.get("limit", 200))
        offset = int(body.get("offset", 0))
        manager = SessionManager()
        messages, total = manager.load_thread(
            int(chatbot_id), limit=limit, offset=offset
        )
        current_mood = None
        try:
            conv = (
                Conversation.objects.query()
                .filter(Conversation.chatbot_id == int(chatbot_id))
                .order_by(Conversation.id.desc())
                .first()
            )
            if conv:
                current_mood = (conv.user_data or {}).get(
                    "current_mood"
                )
        except Exception:
            pass
        if not current_mood:
            from airunner_services.llm.tools.mood_tools import (
                _kaomoji_for_mood,
            )
            for msg in reversed(messages):
                if (
                    isinstance(msg, dict)
                    and msg.get("role") == "assistant"
                    and msg.get("bot_mood")
                    and msg.get("bot_mood") != "neutral"
                ):
                    mood = msg["bot_mood"]
                    emoji = msg.get("bot_mood_emoji", "😐")
                    kaomoji = msg.get("bot_mood_kaomoji") or (
                        _kaomoji_for_mood(mood, "")
                    )
                    current_mood = {
                        "mood": mood,
                        "emoji": emoji,
                        "kaomoji": kaomoji,
                    }
                    break
        return {
            "status": 200,
            "body": {
                "messages": messages,
                "total": total,
                "offset": offset,
                "current_mood": current_mood,
            },
        }
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logger,
            context="thread error",
        )
