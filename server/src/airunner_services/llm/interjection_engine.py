"""Mid-conversation interjection engine.

After the bot responds, it occasionally remembers something extra to add —
like texting "wait" or "actually" a few seconds later.  Fires with low
probability so it feels spontaneous, not spammy.
"""

from __future__ import annotations

import datetime
import logging
import random
import time
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

INTERJECTION_PROBABILITY: float = 0.10
INTERJECTION_MIN_DELAY: int = 10
INTERJECTION_MAX_DELAY: int = 90
MAX_HISTORY: int = 10

_TRIGGER = (
    "[INTERNAL]\n"
    "You are mid-conversation and something just crossed your mind — "
    "a stray thought, a detail you forgot to mention, something you "
    "want to add. Send ONE short follow-up sentence, completely in "
    "character. No questions. No recap of what you just said."
)


def maybe_schedule_interjection(
    owner: Any,
    user_text: str,
    assistant_text: str,
    action: Any,
) -> None:
    """Schedule a spontaneous follow-up for conversational turns."""
    from airunner_services.llm.pipeline_loader import is_enabled
    from airunner_services.llm.managers.prompt_builder.prompt_builder import (
        CONVERSATIONAL_ACTIONS,
    )

    if not is_enabled("INTERJECTION"):
        return
    if action not in CONVERSATIONAL_ACTIONS:
        return
    if not assistant_text or not user_text:
        return
    chatbot = getattr(owner, "chatbot", None)
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not chatbot_id:
        return
    wm = getattr(owner, "_workflow_manager", None)
    chat_model = (
        getattr(wm, "_original_chat_model", None)
        or getattr(wm, "_chat_model", None)
    )
    if not chat_model:
        return
    schedule_interjection(chatbot_id, chat_model)


def schedule_interjection(
    chatbot_id: int,
    chat_model: Any,
    tenant_key: Optional[str] = None,
) -> None:
    """Roll the dice and optionally spawn a delayed interjection thread."""
    from airunner_services.utils.network_retry import is_api_exhausted
    if is_api_exhausted():
        return
    if random.random() > INTERJECTION_PROBABILITY:
        return
    if tenant_key is None:
        from airunner_services.data.tenant import get_tenant_key
        tenant_key = get_tenant_key()
    from airunner_services.data.tenant import get_account_id

    account_id = get_account_id()
    if not account_id:
        logger.warning("Interjection: no account_id — skipping")
        return

    # Write DEK to relay (Tier 2).
    from airunner_services.utils.crypto.dek_cache import get_user_dek
    from airunner_services.tasks.task_helpers import wrap_dek_for_relay
    from airunner_services.tasks.redis_client import dek_relay_store

    user_dek = get_user_dek()
    if user_dek is not None:
        wrapped = wrap_dek_for_relay(user_dek)
        dek_relay_store(account_id, wrapped)

    from airunner_services.tasks.knowledge_tasks import run_interjection

    delay = random.randint(INTERJECTION_MIN_DELAY, INTERJECTION_MAX_DELAY)
    run_interjection.apply_async(
        args=[tenant_key, account_id, chatbot_id],
        queue="default",
        countdown=delay,
    )


def _run(
    chatbot_id: int,
    chat_model: Any,
    tenant_key: Optional[str],
    delay: int,
) -> None:
    """Thread target: sleep, then generate and persist the interjection."""
    time.sleep(delay)
    from airunner_services.data.tenant import tenant_scope

    try:
        with tenant_scope(tenant_key):
            _generate_and_persist(chatbot_id, chat_model)
    except Exception:
        logger.exception(
            "Interjection failed for chatbot %s", chatbot_id
        )


def _generate_and_persist(
    chatbot_id: int, chat_model: Any, account_id: int,
) -> None:
    """Load context, call LLM, persist, and broadcast the message."""
    from airunner_services.database.models.chatbot import Chatbot
    from airunner_services.llm.session_manager import SessionManager

    chatbot = Chatbot.objects.get(chatbot_id)
    if chatbot is None:
        return
    if getattr(chatbot, "has_blocked_user", False):
        return
    if not getattr(chatbot, "is_online", True):
        return

    mgr = SessionManager()
    history, _ = mgr.load_thread(chatbot_id, limit=MAX_HISTORY)

    if _user_replied_since(history):
        return

    response = _call_llm(chatbot, history, chat_model)
    if not response:
        return

    session, conv, _, _ = mgr.get_or_create_session(chatbot_id)
    if conv is None:
        return
    _persist(conv.id, session.id, response, chatbot_id, account_id)


def _user_replied_since(history: List[dict]) -> bool:
    """Return True if the user has already sent a new message."""
    visible = [m for m in history if isinstance(m, dict)]
    return bool(visible) and visible[-1].get("role") == "user"


def _call_llm(chatbot: Any, history: List[dict], chat_model: Any) -> str:
    """Build prompt, call model, return clean text."""
    from types import SimpleNamespace

    from langchain_core.messages import (
        AIMessage as LcAI,
        HumanMessage,
        SystemMessage,
    )

    from airunner_services.llm.managers.prompt_builder import (
        prompt_builder as pb,
    )
    from airunner_services.llm.managers.prompt_builder.identity_parts import (
        _rp_identity_block,
    )
    from airunner_services.llm.managers.prompt_builder.parts import (
        _append_if_present,
        _project_rp_style,
    )

    owner = SimpleNamespace(chatbot=chatbot)
    parts: list[str] = [pb.HARD_RULES, _rp_identity_block(chatbot)]
    _append_if_present(parts, _project_rp_style(owner))
    parts.append(pb.MEMORY_INSTRUCTIONS)
    system = "\n\n".join(parts)

    _role_map = {"assistant": LcAI, "user": HumanMessage}
    messages: list = [SystemMessage(content=system)]
    for m in history:
        cls = _role_map.get(str(m.get("role", "")))
        if cls:
            messages.append(cls(content=str(m.get("content", ""))))
    messages.append(HumanMessage(content=_TRIGGER))

    try:
        result = chat_model.invoke(messages)
        return (getattr(result, "content", "") or "").strip()
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_permanent_client_error,
            mark_api_exhausted,
        )
        if is_permanent_client_error(exc):
            mark_api_exhausted(exc)
            logger.warning(
                "Interjection LLM call failed (permanent): %s", exc
            )
        else:
            logger.debug("Interjection LLM call failed: %s", exc)
        return ""


def _persist(
    conv_id: int,
    session_id: int,
    response: str,
    chatbot_id: int,
    account_id: int,
) -> None:
    """Append trigger + response to conversation and push WS event."""
    from airunner_services.api.routes.events_bus import WsEventBus
    from airunner_services.api.routes.events_rpc import (
        EVENT_PROACTIVE_MESSAGE,
    )
    from airunner_services.database.models.chat_session import ChatSession
    from airunner_services.database.models.conversation import Conversation

    now = datetime.datetime.utcnow()
    ts = now.isoformat()
    conv = Conversation.objects.get(conv_id)
    if conv is None:
        return
    raw = conv.value
    if not isinstance(raw, list):
        logger.error(
            "InterjectionEngine: conversation %s returned non-list "
            "value (type=%s). Skipping interjection append.",
            getattr(conv, "id", "?"),
            type(raw).__name__,
        )
        return
    value = list(raw)
    value.append({
        "role": "user",
        "content": _TRIGGER,
        "metadata_type": "proactive_trigger",
        "session_id": session_id,
        "timestamp": ts,
    })
    value.append({
        "role": "assistant",
        "content": response,
        "metadata_type": "proactive_response",
        "session_id": session_id,
        "timestamp": ts,
    })
    Conversation.objects.update(conv_id, value=value)
    ChatSession.objects.update(session_id, last_message_at=now)

    try:
        from airunner_services.events.recorder import record

        record(
            "message_append",
            chatbot_id=chatbot_id,
            actor="assistant",
            payload={
                "role": "assistant",
                "content": response,
                "thinking_content": None,
                "metadata_type": "interjection",
                "tool_usage": None,
            },
            conversation_id=conv_id,
            session_id=session_id,
            sequence_num=None,
        )
    except Exception:
        pass

    logger.info("Interjection written to conversation %s", conv_id)
    WsEventBus().broadcast(
        EVENT_PROACTIVE_MESSAGE,
        {
            "chatbot_id": chatbot_id,
            "role": "assistant",
            "content": response,
            "conv_id": conv_id,
            "session_id": session_id,
        },
        account_id=account_id,
    )
