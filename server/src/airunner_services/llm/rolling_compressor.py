"""Rolling in-session message compression — fire-and-forget.

After every N assistant turns, compresses messages older than the last
KEEP_RECENT into a rolling summary stored on the ChatSession.  On the
next turn, the history builder prepends the summary and only passes the
last KEEP_RECENT messages to the LLM.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import List

from airunner_services.llm.token_usage import record_background_usage

from airunner_services.conf.model_settings import META_LLAMA_INSTRUCT_MODEL

logger = logging.getLogger(__name__)

_COMPRESSION_PROMPT = (
    "Summarize this conversation segment in 2-3 sentences as the "
    "character {name}. Write as 'I'.\n\n"
    "MESSAGES:\n{messages}\n\n"
    "Return ONLY the summary text, no JSON, no formatting."
)


def _interval() -> int:
    """Return the compression interval from pipeline config, or 0 to disable."""
    from airunner_services.llm.pipeline_loader import (
        pipeline_config,
        is_enabled,
    )
    if not is_enabled("ROLLING_COMPRESSOR"):
        return 0
    return int(
        pipeline_config("ROLLING_COMPRESSOR").get("interval_turns", 6)
    )


def _keep_recent() -> int:
    """Return how many recent messages to keep verbatim."""
    from airunner_services.llm.pipeline_loader import pipeline_config
    return int(
        pipeline_config("ROLLING_COMPRESSOR").get("keep_recent", 8)
    )


def _session_messages(session_id: int) -> List[dict]:
    """Return all chat messages for a session, chronological.

    Tool-call metadata entries are used to annotate the assistant
    message that follows them with a ``tool_names`` key so the
    compression prompt can record that a real search/tool was used.
    ``tool_result``, ``rag_injection``, and ``proactive_trigger``
    entries are still excluded.
    """
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        conversations = (
            Conversation.objects.query()
            .filter(Conversation.session_id == session_id)
            .order_by(Conversation.id.asc())
            .all()
        )
        all_msgs: List[dict] = []
        pending_tool_names: List[str] = []
        for conv in conversations:
            for msg in getattr(conv, "value", None) or []:
                if not isinstance(msg, dict):
                    continue
                mt = msg.get("metadata_type")
                if mt == "tool_calls":
                    for tc in msg.get("tool_calls", []):
                        name = tc.get("name", "")
                        if name and name not in pending_tool_names:
                            pending_tool_names.append(name)
                    continue
                if mt in (
                    "tool_result", "rag_injection", "proactive_trigger",
                ):
                    continue
                if msg.get("role") in ("user", "assistant"):
                    if pending_tool_names and msg.get("role") == "assistant":
                        msg = dict(msg)
                        msg["tool_names"] = list(pending_tool_names)
                        pending_tool_names = []
                    all_msgs.append(msg)
        return all_msgs
    except Exception:
        return []


def _count_assistant_turns(session_id: int) -> int:
    """Count assistant chat messages in the given session."""
    msgs = _session_messages(session_id)
    return sum(1 for m in msgs if m.get("role") == "assistant")


def _build_compression_prompt(
    name: str, messages: List[dict],
) -> str:
    """Build the compression prompt for older messages.

    When an assistant message carries ``tool_names`` (set by
    ``_session_messages`` from preceding ``tool_calls`` metadata),
    appends a ``[used tools: ...]`` annotation so the compression
    LLM knows a real search/tool produced the answer.
    """
    lines: List[str] = []
    for m in messages:
        line = f"{m.get('role', '?').upper()}: {m.get('content', '')[:250]}"
        tool_names = m.get("tool_names")
        if tool_names:
            line += f" [used tools: {', '.join(tool_names)}]"
        lines.append(line)
    return _COMPRESSION_PROMPT.format(
        name=name, messages="\n".join(lines),
    )


def _call_llm(prompt: str) -> str:
    """Call the configured cloud LLM for compression."""
    import traceback
    logger.warning(
        "[STACK TRACE] _call_llm (ROLLING_COMPRESSOR):\n%s",
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

        cfg = pipeline_config("ROLLING_COMPRESSOR")
        model = create_openrouter_model(
            api_key=api_key,
            model_name=cfg.get("model", META_LLAMA_INSTRUCT_MODEL),
            temperature=cfg.get("temperature", 0.3),
            max_tokens=cfg.get("max_tokens", 300),
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
            "ROLLING_COMPRESSOR", cfg, response,
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
                logger, "Rolling compression LLM call failed", exc
            )
        else:
            logger.error(
                "Rolling compression LLM call failed", exc_info=True
            )
        return ""


def _persist_summary(session_id: int, summary: str) -> None:
    """Store the rolling summary on the ChatSession row."""
    try:
        from airunner_services.database.models.chat_session import (
            ChatSession,
        )

        ChatSession.objects.update(
            session_id, rolling_summary=summary,
        )
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
            log_network_failure,
        )
        if is_transient_network_error(exc):
            log_network_failure(
                logger, "Rolling summary persist failed", exc
            )
        else:
            logger.error(
                "Rolling summary persist failed", exc_info=True
            )


async def _compress_async(
    chatbot_name: str, session_id: int,
) -> None:
    """Run the full compression pipeline in the background."""
    try:
        keep = _keep_recent()
        all_msgs = _session_messages(session_id)
        if len(all_msgs) <= keep:
            return
        older = all_msgs[:-keep]
        prompt = _build_compression_prompt(chatbot_name, older)
        raw = _call_llm(prompt)
        if not raw:
            return
        _persist_summary(session_id, raw)
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
            log_network_failure,
        )
        if is_transient_network_error(exc):
            log_network_failure(
                logger, "Rolling compression failed", exc
            )
        else:
            logger.error(
                "Rolling compression failed", exc_info=True
            )


def schedule_rolling_compression(
    chatbot_name: str,
    session_id: int,
) -> None:
    """Fire-and-forget rolling compression if the turn interval elapsed."""
    interval = _interval()
    if interval <= 0:
        return
    if not session_id:
        return
    turn_count = _count_assistant_turns(session_id)
    if turn_count <= 0 or turn_count % interval != 0:
        return
    try:
        asyncio.create_task(
            _compress_async(chatbot_name, session_id)
        )
    except Exception:
        logger.debug("schedule_rolling_compression: task creation failed")


def compress_session_messages(
    session_id: int,
    chatbot_name: str,
) -> None:
    """Compress all messages in a session for session-end processing.

    Unlike schedule_rolling_compression (which fires every N turns and
    keeps recent messages verbatim), this compresses the ENTIRE session
    into a rolling summary.  Called from summarize_session during
    session rotation.
    """
    from airunner_services.llm.pipeline_loader import is_enabled

    if not is_enabled("ROLLING_COMPRESSOR"):
        return
    if not session_id or not chatbot_name:
        return
    all_msgs = _session_messages(session_id)
    if len(all_msgs) < 3:
        return
    try:
        prompt = _build_compression_prompt(chatbot_name, all_msgs)
        raw = _call_llm(prompt)
        if raw:
            _persist_summary(session_id, raw)
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
            log_network_failure,
        )
        if is_transient_network_error(exc):
            log_network_failure(
                logger, "Session-end compression failed", exc
            )
        else:
            logger.error(
                "Session-end compression failed", exc_info=True
            )
