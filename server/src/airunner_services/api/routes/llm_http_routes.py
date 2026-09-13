"""HTTP endpoints for UwU session and thread management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from airunner_services.api.server_middleware import sanitized_http_exception
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

from airunner_services.api.routes.character_utils import (
    build_character_prompt,
    build_uwu_identity_prompt,
    parse_llm_json,
)

if TYPE_CHECKING:
    from airunner_services.api.routes.llm_runtime import LLMRuntimeResult
    from airunner_services.database.models.conversation import Conversation

router = APIRouter()
logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


def _latest_conversation_for(chatbot_id: int) -> Optional[Conversation]:
    """Return the most recent Conversation for a chatbot (any session)."""
    from airunner_services.database.models.conversation import Conversation

    return (
        Conversation.objects.query()
        .filter(Conversation.chatbot_id == chatbot_id)
        .order_by(Conversation.id.desc())
        .first()
    )


class CharacterGenerateRequest(BaseModel):
    species: str = "Human"
    gender: str = "Female"
    vibe: str = "Cozy"
    quirk: str = "Loves snacks"
    affinity: str = "Stars"
    age_era: str = "A Few Decades"


def _record_character_usage(result: LLMRuntimeResult) -> None:
    """Fire-and-forget PipelineTokenUsage for character creation.

    record_usage never raises, so a recording failure can't break the
    create flow.
    """
    from airunner_services.llm.active_call_chain import (
        get_active_call_chain,
    )
    from airunner_services.llm.pipeline_loader import pipeline_config
    from airunner_services.llm.token_usage import record_usage

    cfg = pipeline_config("CHARACTER_CREATION")
    record_usage(
        pipeline_key="CHARACTER_CREATION",
        model_id=cfg.get("model", ""),
        input_tokens=result.prompt_tokens,
        output_tokens=result.completion_tokens,
        call_chain_id=get_active_call_chain(),
    )


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/generate-character")
async def generate_character(
    body: CharacterGenerateRequest, req: Request
) -> dict:
    """Generate a character using the LLM (name, personality, backstory, greeting)."""
    from airunner_services.api.routes.llm_runtime import (
        invoke_llm_runtime,
        require_runtime_registry,
        resolve_llm_client,
    )
    from airunner_services.runtimes.contracts import (
        ChatMessage as RuntimeChatMessage,
        MessageRole,
    )
    from fastapi import HTTPException

    try:
        registry = require_runtime_registry(req)
        client = resolve_llm_client(registry)
    except HTTPException:
        raise

    system_content, user_content = build_character_prompt(
        body.species,
        body.gender,
        body.vibe,
        body.quirk,
        body.affinity,
        body.age_era,
    )
    messages = [
        RuntimeChatMessage(role=MessageRole.SYSTEM, content=system_content),
        RuntimeChatMessage(role=MessageRole.USER, content=user_content),
    ]
    try:
        result = await invoke_llm_runtime(
            client, messages, None, None, 0.9, 500, stateless=True
        )
    except Exception as exc:
        raise sanitized_http_exception(
            exc,
            logger=logger,
            context="generate-character LLM error",
        )
    _record_character_usage(result)
    try:
        return parse_llm_json(result.content)
    except ValueError as exc:
        raise sanitized_http_exception(
            exc,
            logger=logger,
            context="generate-character parse error",
        )


class UwuIdentityRequest(BaseModel):
    gender: str = "Female"
    personality_type: str = "Sweet & Nurturing"
    species_data: dict | None = None
    location: dict | None = None
    age: int | None = None


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/generate-uwu-identity")
async def generate_uwu_identity(
    body: UwuIdentityRequest, req: Request
) -> dict:
    """Generate name/personality/backstory/greeting for a random UwU."""
    from airunner_services.api.routes.llm_runtime import (
        invoke_llm_runtime,
        require_runtime_registry,
        resolve_llm_client,
    )
    from airunner_services.runtimes.contracts import (
        ChatMessage as RuntimeChatMessage,
        MessageRole,
    )
    from fastapi import HTTPException

    try:
        registry = require_runtime_registry(req)
        client = resolve_llm_client(registry)
    except HTTPException:
        raise

    system_content, user_content = build_uwu_identity_prompt(
        body.gender,
        body.personality_type,
        species_data=body.species_data,
        location=body.location,
        age=body.age,
    )
    messages = [
        RuntimeChatMessage(role=MessageRole.SYSTEM, content=system_content),
        RuntimeChatMessage(role=MessageRole.USER, content=user_content),
    ]
    try:
        result = await invoke_llm_runtime(
            client, messages, None, None, 0.9, 500, stateless=True
        )
    except Exception as exc:
        raise sanitized_http_exception(
            exc,
            logger=logger,
            context="generate-uwu-identity LLM error",
        )
    _record_character_usage(result)
    try:
        return parse_llm_json(result.content)
    except ValueError as exc:
        raise sanitized_http_exception(
            exc,
            logger=logger,
            context="generate-uwu-identity parse error",
        )


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/uwu-session")
async def get_uwu_session(chatbot_id: int = Query(...), req: Request = None):
    """Get or create the active session for a chatbot.

    Returns ``{conversation_id, session_id}`` so the client can track the
    current conversation for streaming.  Session rotation and lazy
    episodic summarisation are triggered here when the 4-hour gap is exceeded.
    """
    try:
        from airunner_services.llm.session_manager import (
            SessionManager,
        )
        from airunner_services.database.models.chatbot import Chatbot
        from fastapi import HTTPException

        chatbot = Chatbot.objects.get(chatbot_id)
        if not chatbot or getattr(chatbot, "deleted", False):
            raise HTTPException(
                status_code=404, detail=f"Chatbot {chatbot_id} not found"
            )

        manager = SessionManager()
        session, conv, _cold_id, _gap_hours = manager.get_or_create_session(
            chatbot_id
        )
        # A fresh session has no linked Conversation yet (created on first
        # send); bind the UI to the most recent one the user is viewing.
        if conv is None:
            conv = _latest_conversation_for(chatbot_id)

        return {
            "conversation_id": getattr(conv, "id", None),
            "session_id": getattr(session, "id", None),
        }
    except Exception as exc:
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            raise
        raise sanitized_http_exception(
            exc,
            logger=logger,
            context="uwu-session error",
        )


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/thread")
async def get_uwu_thread(
    chatbot_id: int = Query(...),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Return the full persistent message thread for a chatbot.

    Messages span all sessions, ordered chronologically.  Each message
    includes ``session_id`` and ``session_started_at`` so the frontend can
    render session-gap dividers.
    """
    try:
        from airunner_services.llm.session_manager import SessionManager
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        manager = SessionManager()
        messages, total = manager.load_thread(
            chatbot_id, limit=limit, offset=offset
        )
        current_mood = None
        try:
            conv = (
                Conversation.objects.query()
                .filter(Conversation.chatbot_id == chatbot_id)
                .order_by(Conversation.id.desc())
                .first()
            )
            if conv:
                current_mood = (conv.user_data or {}).get(
                    "current_mood"
                )
                logger.warning(
                    "[MOOD DEBUG] thread endpoint chatbot_id=%s "
                    "conv_id=%s user_data=%r "
                    "current_mood=%r",
                    chatbot_id, conv.id,
                    conv.user_data, current_mood,
                )
        except Exception:
            pass
        # Fall back to the last assistant message that carries mood
        # data — covers cases where background persist didn't run.
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
            "messages": messages,
            "total": total,
            "offset": offset,
            "current_mood": current_mood,
        }
    except Exception as exc:
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            raise
        raise sanitized_http_exception(
            exc,
            logger=logger,
            context="thread error",
        )
