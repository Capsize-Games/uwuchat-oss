"""Episodic memory summarizer — generates LLM narrative for cold sessions."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from airunner_services.llm.token_usage import record_background_usage

from airunner_services.conf.model_settings import META_LLAMA_INSTRUCT_MODEL
from airunner_services.contract_enums import ModelService

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = (
    "A conversation session just ended.\n"
    "CHARACTER: {character}\n"
    "MESSAGES:\n{messages}\n\n"
    "Write a memory entry as {character}.\n"
    "PERSPECTIVE RULES (critical):\n"
    "- You ARE {character}. Write as 'I'. Never use {character}'s name.\n"
    "- The other person is 'the user' or 'they'.\n"
    "- Their life (family, job, feelings) is something THEY shared with you,"
    " not something that belongs to you.\n"
    "- Wrong: 'I'm relieved my wife is healing.' (that's the user's wife)\n"
    "- Right: 'They told me their wife is healing. I was glad to hear it.'\n\n"
    "Include: what was discussed, what the user revealed, emotional tone,"
    " any shift in your inner state.\n\n"
    "Return ONLY a JSON object:\n"
    "{{\n"
    '  "summary": "1-3 sentence narrative memory",\n'
    '  "emotional_weight": 0.0-1.0,\n'
    '  "key_topics": ["topic1", "topic2"]\n'
    "}}\n\n"
    "emotional_weight: 0.0 = forgettable, 1.0 = highly significant."
)


def _build_summary_prompt(chatbot_name: str, messages: list[dict]) -> str:
    """Format the summarization prompt."""
    visible = [
        m
        for m in messages
        if isinstance(m, dict)
        and m.get("metadata_type") != "proactive_trigger"
        and m.get("role") in ("user", "assistant")
    ]
    msg_text = "\n".join(
        f"{m.get('role', '?').upper()}: {m.get('content', '')[:300]}"
        for m in visible[:40]
    )
    return _SUMMARY_PROMPT.format(character=chatbot_name, messages=msg_text)


def _parse_summary(raw: str) -> Optional[dict]:
    """Extract JSON from LLM response."""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(raw[start:end])
    except Exception:
        return None


def _call_llm(app: Any, prompt: str) -> str:
    """Call the LLM — tries local runtime then falls back to cloud."""
    result = _try_local_runtime(app, prompt)
    if result:
        return result
    return _try_cloud_llm(prompt)


def _try_local_runtime(app: Any, prompt: str) -> str:
    """Attempt to call the local LLM runtime."""
    from airunner_services.runtimes.contracts import (
        ChatMessage as Msg,
        LLMInvocationRequest,
        MessageRole,
        RuntimeAction,
        RuntimeKind,
    )
    from airunner_services.ipc.messages import EnvelopeStatus, RequestEnvelope

    try:
        registry = getattr(
            getattr(app, "state", None), "runtime_registry", None
        )
        if registry is None:
            return ""
        client = registry.resolve(RuntimeKind.LLM, provider=ModelService.LOCAL.value)
        msgs = [Msg(role=MessageRole.USER, content=prompt)]
        inv = LLMInvocationRequest(
            messages=msgs,
            metadata={"stateless": True},
            temperature=0.6,
            max_tokens=500,
        )
        env = RequestEnvelope(
            runtime=RuntimeKind.LLM,
            action=RuntimeAction.INVOKE,
            provider=ModelService.LOCAL.value,
            payload=inv.model_dump(),
        )
        resp = client.invoke(env)
        if resp.status is not EnvelopeStatus.SUCCEEDED:
            return ""
        return str(resp.payload.get("content", ""))
    except Exception:
        return ""


def _try_cloud_llm(prompt: str) -> str:
    """Call a cloud LLM directly for summarization."""
    import os
    import traceback
    logger.warning(
        "[STACK TRACE] _try_cloud_llm (EPISODIC_SUMMARIZER):\n%s",
        "".join(traceback.format_stack()),
    )

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
        cfg = pipeline_config("EPISODIC_SUMMARIZER")
        model = create_openrouter_model(
            api_key=api_key,
            model_name=cfg.get("model", META_LLAMA_INSTRUCT_MODEL),
            temperature=cfg.get("temperature", 0.3),
            max_tokens=cfg.get("max_tokens", 500),
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
            "EPISODIC_SUMMARIZER", cfg, response,
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
        return str(getattr(response, "content", response) or "").strip()
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
            log_network_failure,
        )
        if is_transient_network_error(exc):
            log_network_failure(
                logger, "Cloud LLM summary call failed", exc
            )
        else:
            logger.error(
                "Cloud LLM summary call failed", exc_info=True
            )
        return ""


async def summarize_session(session_id: int, app: Any = None) -> None:
    """Generate and persist an episodic summary for a cold session.

    Runs the synchronous summarization cascade in a worker thread so
    it never blocks the event loop that serves concurrent requests.
    """
    await asyncio.to_thread(_summarize_session_sync, session_id, app)


def _get_recent_conversation_id(conversations: list) -> Optional[int]:
    """Return the highest id from a list of conversation objects."""
    if not conversations:
        return None
    return max(getattr(c, "id", 0) for c in conversations)


def _update_mood_if_recent(
    conversations: list,
    session_id: int,
    name: str,
    chatbot_id: int,
) -> None:
    """Update chatbot mood from the most recent conversation."""
    recent_conv_id = _get_recent_conversation_id(conversations)
    if not recent_conv_id:
        return
    try:
        from airunner_services.llm.mood import update_mood_from_session

        update_mood_from_session(
            session_id, name, recent_conv_id,
            chatbot_id=chatbot_id,
        )
    except Exception:
        logger.debug("Session-end mood update skipped")


def _run_post_summary_cascade(
    session_id: int,
    chatbot_id: int,
    name: str,
    conversations: list,
    messages: list,
    summary: Optional[str],
    app: Any,
    chatbot: Any,
) -> None:
    """Run the post-summary cascade: compress, mood, curiosity,
    voice samples, memory update, and semantic memory extraction."""
    try:
        from airunner_services.llm.rolling_compressor import (
            compress_session_messages,
        )
        compress_session_messages(session_id, name)
    except Exception:
        logger.debug("Rolling compressor skipped")

    _update_mood_if_recent(conversations, session_id, name, chatbot_id)

    if chatbot_id:
        try:
            from airunner_services.llm.curiosity_engine import (
                generate_session_curiosity,
            )
            generate_session_curiosity(session_id, chatbot_id)
        except Exception:
            logger.debug("Session-end curiosity skipped")

    if chatbot:
        from airunner_services.llm.episodic_voice_samples import (
            extract_voice_samples,
        )
        extract_voice_samples(chatbot, session_id, messages)

    if chatbot_id:
        try:
            from airunner_services.llm.memory_updater import (
                index_session_turns,
                update_agent_memory,
            )
            index_session_turns(session_id, chatbot_id)
            if summary:
                update_agent_memory(chatbot_id, summary, app=app)
        except Exception as exc:
            from airunner_services.utils.network_retry import (
                is_transient_network_error,
                log_network_failure,
            )
            if is_transient_network_error(exc):
                log_network_failure(
                    logger, "Memory updater skipped", exc
                )
            else:
                logger.error("Memory updater skipped", exc_info=True)

    if app is not None and chatbot_id:
        try:
            from airunner_services.world.semantic_memory import (
                SemanticMemoryExtractor,
            )
            SemanticMemoryExtractor(app).extract(
                session_id, chatbot_id
            )
        except Exception:
            logger.debug("Semantic memory extraction skipped")


def _summarize_session_sync(session_id: int, app: Any = None) -> None:
    """Generate and persist an episodic summary for a cold session."""
    try:
        from airunner_services.database.models.chat_session import ChatSession
        from airunner_services.database.models.conversation import Conversation
        from airunner_services.database.models.chatbot import Chatbot

        session = ChatSession.objects.get(session_id)
        if session is None or session.summary_ready:
            return

        conversations = (
            Conversation.objects.query()
            .filter(Conversation.session_id == session_id)
            .all()
        )
        messages = []
        for conv in conversations:
            messages.extend(getattr(conv, "value", None) or [])

        if not messages:
            ChatSession.objects.update(session_id, summary_ready=True)
            return

        chatbot = Chatbot.objects.get(session.chatbot_id)
        name = (
            getattr(chatbot, "botname", "Unknown")
            if chatbot else "Unknown"
        )

        prompt = _build_summary_prompt(name, messages)
        raw = ""
        if app is not None:
            raw = _try_local_runtime(app, prompt)
        if not raw:
            raw = _try_cloud_llm(prompt)
        result: Optional[dict] = _parse_summary(raw) if raw else None

        if result is None:
            result = _lexrank_fallback(messages)

        summary = (result or {}).get("summary") if result else None
        weight = (result or {}).get("emotional_weight")
        topics = (result or {}).get("key_topics") or []

        ChatSession.objects.update(
            session_id,
            episodic_summary=summary,
            emotional_weight=weight,
            key_topics=topics if topics else None,
            summary_ready=True,
        )

        _run_post_summary_cascade(
            session_id=session_id,
            chatbot_id=session.chatbot_id,
            name=name,
            conversations=conversations,
            messages=messages,
            summary=summary,
            app=app,
            chatbot=chatbot,
        )
    except Exception:
        logger.exception("summarize_session failed for %s", session_id)


def _lexrank_fallback(messages: list[dict]) -> Optional[dict]:
    """Extract a summary via LexRank when the LLM is unavailable."""
    try:
        all_text = " ".join(
            m.get("content", "")
            for m in messages
            if isinstance(m, dict) and m.get("role") in ("user", "assistant")
        )
        if not all_text.strip():
            return None
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.summarizers.lex_rank import LexRankSummarizer

        parser = PlaintextParser.from_string(all_text, Tokenizer("english"))
        summarizer = LexRankSummarizer()
        sentences = summarizer(parser.document, 2)
        text = " ".join(str(s) for s in sentences).strip()
        return {"summary": text or None, "emotional_weight": 0.3}
    except Exception:
        return None


