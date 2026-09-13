"""Post-turn curiosity engine — identifies knowledge gaps and queues one question.

Flow per completed response:
  1. Daemon thread starts with the last exchange + known facts for this chatbot.
  2. A single LLM call identifies one entity the user mentioned that is missing
     a natural follow-up detail.
  3. Result is upserted into curiosity_questions (one row per chatbot).
  4. The per-turn context injector reads and clears it before the next response.
"""

from __future__ import annotations

import json
import logging
import threading

from airunner_services.conf.model_settings import GOOGLE_GEMINI_FLASH_LITE_MODEL

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You find one knowledge gap worth asking about in a conversation.\n\n"
    "Given known facts about the user and the most recent exchange, identify\n"
    "ONE entity the user mentioned where a natural follow-up question exists.\n\n"
    "Rules:\n"
    "- The entity must come only from what the USER wrote, not the assistant.\n"
    "- Skip anything already covered by the known facts.\n"
    "- Prefer personal details: names, relationships, places, life events.\n"
    "- The question should feel like genuine curiosity, not data collection.\n"
    "- If nothing is genuinely worth asking, output exactly: null\n\n"
    "Output JSON only (no markdown, no explanation):\n"
    '{"entity": "...", "missing": "...", "question": "..."}\n'
    "or: null"
)


def _should_run(
    session_id: "int | None",
    complexity_score: float = 0.0,
) -> bool:
    """Return True if pipeline config allows curiosity on this turn."""
    from airunner_services.llm.pipeline_loader import (
        pipeline_config,
        is_enabled,
    )
    if not is_enabled("CURIOSITY_ENGINE"):
        return False
    cfg = pipeline_config("CURIOSITY_ENGINE")
    if complexity_score < cfg.get("min_complexity", 0.0):
        return False
    interval = int(cfg.get("interval_turns", 3))
    if interval <= 0 or session_id is None:
        return interval > 0
    try:
        from airunner_services.database.models.conversation import Conversation
        convs = (
            Conversation.objects.query()
            .filter(Conversation.session_id == session_id)
            .all()
        )
        count = sum(
            1
            for c in convs
            for m in (getattr(c, "value", None) or [])
            if isinstance(m, dict) and m.get("role") == "assistant"
        )
        return count > 0 and count % interval == 0
    except Exception:
        return True


def schedule_curiosity(
    chatbot_id: int,
    user_text: str,
    assistant_text: str,
    chat_model,
    tenant_key: "str | None" = None,
    session_id: "int | None" = None,
    complexity_score: float = 0.0,
) -> None:
    """Fire-and-forget daemon thread to find one curiosity gap."""
    from airunner_services.utils.network_retry import is_api_exhausted
    if is_api_exhausted():
        return
    if not user_text:
        return
    if not _should_run(session_id, complexity_score):
        return
    t = threading.Thread(
        target=_find_and_store,
        args=(chatbot_id, user_text, assistant_text, chat_model, tenant_key),
        daemon=True,
        name="curiosity-engine",
    )
    t.start()


def _find_and_store(
    chatbot_id: int,
    user_text: str,
    assistant_text: str,
    chat_model,
    tenant_key: "str | None" = None,
) -> None:
    """Thread target: call LLM, parse result, upsert pending question."""
    from airunner_services.data.tenant import tenant_scope

    try:
        with tenant_scope(tenant_key):
            fact_lines = _load_facts(chatbot_id)
            data = _call_model(
                chat_model, user_text, assistant_text, fact_lines
            )
            if data:
                _upsert_question(chatbot_id, **data)
    except Exception as exc:
        logger.warning("[CURIOSITY] Failed: %s", exc)


def _load_facts(chatbot_id: int) -> str:
    """Return the known user facts for this chatbot as bullet lines."""
    try:
        from airunner_services.database.models.knowledge_fact import (
            KnowledgeFact,
        )

        rows = (
            KnowledgeFact.objects.query()
            .filter(
                KnowledgeFact.chatbot_id == chatbot_id,
                KnowledgeFact.subject == "user",
                KnowledgeFact.deleted.is_(False),
            )
            .limit(30)
            .all()
        )
        if not rows:
            return "None."
        return "\n".join(f"- {r.fact_text}" for r in rows)
    except Exception:
        return "None."


def _call_model(
    chat_model,
    user_text: str,
    assistant_text: str,
    fact_lines: str,
) -> "dict | None":
    """Return parsed curiosity data dict, or None when nothing is worth asking."""
    from langchain_core.messages import HumanMessage, SystemMessage

    human = (
        f"Known facts about the user:\n{fact_lines}\n\n"
        f"Recent exchange:\n"
        f"User: {user_text}\n"
        f"Assistant: {assistant_text}"
    )
    try:
        from airunner_services.cloud.llm.completion_choke import (
            invoke_with_limiter,
        )
        response = invoke_with_limiter(
            chat_model,
            [SystemMessage(content=_SYSTEM), HumanMessage(content=human)],
            priority="bulk",
        )
        text = (getattr(response, "content", "") or "").strip()
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_permanent_client_error,
            is_transient_network_error,
            log_network_failure,
            mark_api_exhausted,
        )
        if is_permanent_client_error(exc):
            mark_api_exhausted(exc)
            logger.warning(
                "[CURIOSITY] Model call failed (permanent): %s", exc
            )
        elif is_transient_network_error(exc):
            log_network_failure(
                logger, "[CURIOSITY] Model call failed", exc
            )
        else:
            logger.error(
                "[CURIOSITY] Model call failed: %s", exc, exc_info=True
            )
        return None
    if not text or text.lower().strip() == "null":
        return None
    data = _extract_json(text)
    if data is None:
        logger.debug("[CURIOSITY] Could not parse JSON from: %.120s", text)
        return None
    if not isinstance(data, dict):
        return None
    entity = str(data.get("entity", "")).strip()
    missing = str(data.get("missing", "")).strip()
    question = str(data.get("question", "")).strip()
    if not entity or not missing or not question:
        return None
    return {
        "entity": entity[:200],
        "missing": missing[:200],
        "question": question[:400],
    }


def _extract_json(text: str) -> "dict | None":
    """Find and parse the first JSON object in text, ignoring preamble."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except (json.JSONDecodeError, ValueError):
        return None


def _upsert_question(
    chatbot_id: int, entity: str, missing: str, question: str
) -> None:
    """Write or overwrite the one pending curiosity question for this chatbot."""
    from airunner_services.database.models.curiosity_question import (
        CuriosityQuestion,
    )

    existing = CuriosityQuestion.objects.filter_by_first(
        chatbot_id=chatbot_id
    )
    if existing:
        CuriosityQuestion.objects.update(
            pk=existing.id,
            entity=entity,
            missing=missing,
            question=question,
        )
    else:
        CuriosityQuestion.objects.create(
            chatbot_id=chatbot_id,
            entity=entity,
            missing=missing,
            question=question,
        )
    logger.info(
        "[CURIOSITY] Queued for chatbot %s (question_len=%d)",
        chatbot_id,
        len(question),
    )


def generate_session_curiosity(
    session_id: int,
    chatbot_id: int,
) -> None:
    """Generate one curiosity question from the full session arc.

    Unlike schedule_curiosity (which fires per-turn with only the last
    exchange), this reads the complete session to find richer knowledge
    gaps.  Called from summarize_session during session rotation.
    """
    import traceback
    logger.warning(
        "[STACK TRACE] generate_session_curiosity (CURIOSITY_ENGINE):\n%s",
        "".join(traceback.format_stack()),
    )

    from airunner_services.llm.pipeline_loader import is_enabled

    if not is_enabled("CURIOSITY_ENGINE"):
        return
    if not session_id or not chatbot_id:
        return
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )
        from airunner_services.cloud.llm.model_builders import (
            create_openrouter_model,
        )
        from langchain_core.messages import HumanMessage, SystemMessage

        conversations = (
            Conversation.objects.query()
            .filter(Conversation.session_id == session_id)
            .all()
        )
        messages = []
        for conv in conversations:
            messages.extend(getattr(conv, "value", None) or [])
        visible = [
            m for m in messages
            if isinstance(m, dict)
            and m.get("role") in ("user", "assistant")
            and m.get("content")
            and m.get("metadata_type") != "proactive_trigger"
        ]
        if len(visible) < 2:
            return

        fact_lines = _load_facts(chatbot_id)
        convo_text = "\n".join(
            f"{m.get('role', '?').upper()}: {m.get('content', '')[:300]}"
            for m in visible[-20:]
        )
        human = (
            f"Known facts about the user:\n{fact_lines}\n\n"
            f"Full session conversation:\n{convo_text}"
        )
        import os
        from airunner_services.llm.pipeline_loader import pipeline_config

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return
        cfg = pipeline_config("CURIOSITY_ENGINE")
        chat_model = create_openrouter_model(
            api_key=api_key,
            model_name=cfg.get(
                "model", GOOGLE_GEMINI_FLASH_LITE_MODEL
            ),
            temperature=cfg.get("temperature", 0.3),
            max_tokens=cfg.get("max_tokens", 200),
        )

        # ---- PII masking: mask fact/conversation text before LLM egress ----
        # This path is disconnected from CloudModelManager (no per-request
        # _pii_vault), so we construct a standalone vault scoped to this
        # call.  The model's output is a curiosity question (e.g. "Who is
        # Alice?") that never contains the original PII values, so no
        # restoration is needed.
        masked_human = human
        try:
            from airunner_services.llm.pii.settings import (
                PII_MASKING_ENABLED,
            )
            if PII_MASKING_ENABLED:
                from airunner_services.llm.pii.vault import PIIVault
                from airunner_services.llm.pii.masker import mask_text

                vault = PIIVault()
                masked_human = mask_text(human, vault)
        except Exception:
            pass
        # ---- end PII ----

        from airunner_services.cloud.llm.completion_choke import (
            invoke_with_limiter,
        )
        response = invoke_with_limiter(
            chat_model,
            [SystemMessage(content=_SYSTEM),
             HumanMessage(content=masked_human)],
            priority="bulk",
        )
        text = (getattr(response, "content", "") or "").strip()
        from airunner_services.data.tenant import get_tenant_key
        from airunner_services.llm.token_usage import (
            record_background_usage,
            record_pipeline_call_text,
        )
        usage_id = record_background_usage(
            "CURIOSITY_ENGINE", cfg, response,
            chatbot_id=chatbot_id,
            tenant_key=get_tenant_key(),
            prompt_char_count=len(masked_human) if masked_human else None,
            response_char_count=len(text) if text else None,
        )
        record_pipeline_call_text(
            usage_id=usage_id,
            tenant_key=get_tenant_key(),
            prompt_text=masked_human,
            response_text=text,
        )
        if not text or text.lower().strip() == "null":
            return
        data = _extract_json(text)
        if not isinstance(data, dict):
            return
        entity = str(data.get("entity", "")).strip()
        missing = str(data.get("missing", "")).strip()
        question = str(data.get("question", "")).strip()
        if entity and missing and question:
            _upsert_question(chatbot_id, entity, missing, question)
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
            log_network_failure,
        )
        if is_transient_network_error(exc):
            log_network_failure(
                logger,
                "Session-end curiosity generation failed",
                exc,
            )
        else:
            logger.error(
                "Session-end curiosity generation failed",
                exc_info=True,
            )
