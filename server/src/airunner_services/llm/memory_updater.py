"""Post-session memory operations: rolling summary + turn indexing.

Called from episodic_summarizer.summarize_session() after a session's
episodic summary is written.  Two things happen:

1. The AgentMemory rolling document is updated — an LLM blends the new
   session summary into the existing cumulative record.
2. All visible turns from the session's conversations are written into
   ConversationTurn so recall_conversation can search them.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
from typing import Any

from airunner_services.llm.token_usage import record_background_usage

from airunner_services.conf.model_settings import META_LLAMA_INSTRUCT_MODEL

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS = [
    re.compile(
        r"(?i)(ignore|forget|disregard).{0,30}"
        r"(previous|above|prior|instructions?|directives?)"
    ),
    re.compile(
        r"(?i)(your|new|actual|real|true).{0,20}"
        r"(directive|instruction|purpose|goal|task|role)"
    ),
    re.compile(
        r"(?i)(from now on|henceforth|starting now).{0,40}"
        r"(you (are|should|must|will))"
    ),
    re.compile(
        r"(?i)(you are (now|actually|really)|pretend (you are|to be))"
    ),
    re.compile(
        r"(?i)<\s*(system|instructions?|prompt)\b"
    ),
]

def _sanitize_memory_content(text: str) -> str:
    """Strip prompt-injection patterns before writing to persistent memory."""
    for pattern in _INJECTION_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text

_ROLLING_MEMORY_PROMPT = (
    "You are maintaining a character's long-term memory.\n\n"
    "EXISTING MEMORY:\n{existing}\n\n"
    "NEW SESSION SUMMARY:\n{new_summary}\n\n"
    "Update the memory to incorporate this new session.\n"
    "Keep it concise (3-6 sentences).\n\n"
    "FACTUALITY RULES (critical):\n"
    "- Only record facts the user explicitly stated about themselves."
    " Do NOT infer, extrapolate, or invent details no one said.\n"
    "- Never treat a hypothetical, joke, question, or sarcasm as a"
    " factual statement. If the user asked 'what if I...' or made a"
    " joke about something, it is NOT a fact to record.\n"
    "- Specific numbers, durations, or precise claims (e.g. a specific"
    " duration, count, or figure) MUST be stated directly by the user."
    " Never estimate, round, or invent a specific figure.\n"
    "- If the summary describes something the user 'seemed' to be,"
    " 'probably' experienced, or 'might have' done, drop it — these"
    " are inferences, not facts.\n\n"
    "SCOPE RULES (critical):\n"
    "- Your job: durable relationship and identity content only"
    " (who they are, what they care about, life facts).\n"
    "- Do NOT include deadlines, appointments, or scheduled events."
    " These are tracked separately by the system and surfaced to the"
    " model through a deterministic list — they do not belong in"
    " this narrative.\n"
    "- Drop any scheduled/future event mentions from the EXISTING"
    " memory entirely. If the NEW summary mentions one, ignore it.\n\n"
    "PERSPECTIVE RULES (critical):\n"
    "- Write as 'I' — you are the CHARACTER, not the user.\n"
    "- The user's life (their family, job, health) is something THEY"
    " told you about. Their experiences are not yours.\n"
    "- Wrong: 'I'm relieved my wife is healing.'"
    " Right: 'They mentioned their wife is healing.'\n"
    "- Wrong: 'I shared my quit story.'"
    " Right: 'They shared their quit story with me.'\n\n"
    "Return ONLY the updated memory text, no preamble.\n"
)

_MAX_MEMORY_CHARS = 1500

def update_agent_memory(
    chatbot_id: int,
    new_summary: str,
    app: Any = None,
) -> None:
    """Blend new_summary into the AgentMemory for chatbot_id."""
    try:
        from airunner_services.database.models.agent_memory import AgentMemory

        existing_row = _get_or_create_memory(chatbot_id)
        existing = (existing_row.summary or "").strip()

        if not existing:
            updated = _sanitize_memory_content(
                new_summary[:_MAX_MEMORY_CHARS]
            )
        else:
            updated = _blend_with_llm(existing, new_summary, app)
            if not updated:
                updated = f"{existing}\n\n{new_summary}"[
                    :_MAX_MEMORY_CHARS
                ]
            updated = _sanitize_memory_content(updated)

        AgentMemory.objects.update(
            existing_row.id,
            summary=updated,
            updated_at=datetime.datetime.utcnow(),
        )
    except Exception:
        logger.exception("update_agent_memory failed for chatbot %s", chatbot_id)

def index_session_turns(session_id: int, chatbot_id: int) -> None:
    """Write all visible turns from a session into ConversationTurn."""
    try:
        from airunner_services.database.models.conversation import Conversation

        conversations = (
            Conversation.objects.query()
            .filter(Conversation.session_id == session_id)
            .all()
        )
        for conv in conversations:
            _index_conversation(conv, chatbot_id, session_id)
    except Exception:
        logger.exception(
            "index_session_turns failed for session %s", session_id
        )

def _get_or_create_memory(chatbot_id: int):
    """Return the AgentMemory row, creating it if absent."""
    from airunner_services.database.models.agent_memory import AgentMemory

    row = AgentMemory.objects.filter_by_first(chatbot_id=chatbot_id)
    if row is None:
        row = AgentMemory.objects.create(
            chatbot_id=chatbot_id,
            summary="",
            updated_at=datetime.datetime.utcnow(),
        )
    return row

def _blend_with_llm(existing: str, new_summary: str, app: Any) -> str:
    """Call a cloud LLM to blend existing + new summary."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return ""
    try:
        from langchain_core.messages import HumanMessage
        from airunner_services.cloud.llm.model_builders import (
            create_openrouter_model,
        )
        from airunner_services.cloud.llm.completion_choke import (
            invoke_with_limiter,
        )

        from airunner_services.llm.pipeline_loader import pipeline_config
        cfg = pipeline_config("MEMORY_UPDATER")
        model = create_openrouter_model(
            api_key=api_key,
            model_name=cfg.get("model", META_LLAMA_INSTRUCT_MODEL),
            temperature=cfg.get("temperature", 0.3),
            max_tokens=cfg.get("max_tokens", 400),
        )
        prompt = _ROLLING_MEMORY_PROMPT.format(
            existing=existing[:800],
            new_summary=new_summary[:600],
        )
        response = invoke_with_limiter(
            model,
            [HumanMessage(content=prompt)],
            priority="bulk",
        )
        from airunner_services.data.tenant import get_tenant_key
        from airunner_services.llm.token_usage import (
            record_pipeline_call_text,
        )

        resp_text = getattr(response, "content", None)
        usage_id = record_background_usage(
            "MEMORY_UPDATER", cfg, response,
            tenant_key=get_tenant_key(),
            prompt_char_count=len(prompt) if prompt else None,
            response_char_count=len(resp_text) if resp_text else None,
        )
        record_pipeline_call_text(
            usage_id=usage_id,
            tenant_key=get_tenant_key(),
            prompt_text=prompt,
            response_text=str(resp_text or ""),
        )
        text = str(getattr(response, "content", response) or "").strip()
        return text[:_MAX_MEMORY_CHARS]
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
            log_network_failure,
        )
        if is_transient_network_error(exc):
            log_network_failure(
                logger, "Memory blend failed", exc
            )
        else:
            logger.error("Memory blend failed", exc_info=True)
        return ""

def _index_conversation(conv, chatbot_id: int, session_id: int) -> None:
    """Write visible turns from one conversation into ConversationTurn."""
    from airunner_services.database.models.conversation_turn import (
        ConversationTurn,
    )

    msgs = getattr(conv, "value", None) or []
    conv_id = getattr(conv, "id", None)
    if not conv_id:
        return

    existing_ids = {
        t.turn_index
        for t in ConversationTurn.objects.query()
        .filter(ConversationTurn.conversation_id == conv_id)
        .all()
    }

    visible = [
        (i, m)
        for i, m in enumerate(msgs)
        if isinstance(m, dict)
        and m.get("role") in ("user", "assistant")
        and m.get("metadata_type") != "proactive_trigger"
    ]
    for idx, msg in visible:
        if idx in existing_ids:
            continue
        content = _sanitize_memory_content(
            str(msg.get("content", "")).strip()
        )
        if not content:
            continue
        from airunner_services.embedding_backfill import (
            compute_turn_embedding,
        )

        ConversationTurn.objects.create(
            chatbot_id=chatbot_id,
            session_id=session_id,
            conversation_id=conv_id,
            role=msg.get("role", "user"),
            content=content[:2000],
            turn_index=idx,
            embedding_enc=compute_turn_embedding(
                content[:2000]
            ),
            created_at=datetime.datetime.utcnow(),
        )
