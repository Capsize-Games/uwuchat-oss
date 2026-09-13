"""Finalization helpers extracted from generation_execution_support."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from airunner_services.llm.managers.mixins.generation_stream_support import (
    emit_visible_response,
    extract_final_response,
    extract_usage_tokens,
    fallback_response_for_empty_result,
    send_end_of_message,
)
from airunner_services.llm.safety.output_leak_scan import (
    scan_output_for_leaks,
)
from airunner_services.llm.managers.mixins.generation_usage import (
    estimate_token_counts,
)
from airunner_services.llm.token_usage import record_usage
from airunner_services.data.tenant import get_tenant_key

_logger = logging.getLogger(__name__)

_REFLECTION_PROMPT = (
    "You just sent this message to the user:\n"
    '"""\n{response}\n"""\n\n'
    "IMPORTANT: Only choose block_user if the user has been genuinely "
    "abusive, threatening, or has repeatedly violated clearly stated "
    "boundaries AFTER explicit warnings.  A normal conversation — even "
    "one where you disagree or feel uncomfortable — does NOT warrant "
    "blocking.  If you are unsure, choose 'none'.\n\n"
    "Based on what you said, do you need to:\n"
    "- block_user (ONLY for serious abuse/threats after warnings)\n"
    "- none (default — do nothing)\n\n"
    "Reply with ONLY the tool name or 'none'. No explanation."
)


def _run_reflection(owner, response_text: str) -> Optional[str]:
    """Ask the LLM whether it wants to block/leave based on its own message."""
    from airunner_services.utils.network_retry import is_api_exhausted
    if is_api_exhausted():
        return None
    chatbot = getattr(owner, "chatbot", None)
    if not chatbot or getattr(chatbot, "has_blocked_user", False):
        return None
    if getattr(chatbot, "is_system_bot", False):
        # The system dialogue bot never roleplays a persona with
        # relationship boundaries, so blocking the user is never an
        # in-character action for it. Reserved for roleplay chatbots.
        return None
    chat_model = getattr(owner, "_chat_model", None)
    if chat_model is None:
        return None
    prompt = _REFLECTION_PROMPT.format(response=response_text)
    try:
        from langchain_core.messages import HumanMessage
        original_temp = getattr(chat_model, "temperature", 0.7)
        try:
            setattr(chat_model, "temperature", 0.0)
            result = chat_model.invoke(
                [HumanMessage(content=prompt)],
                max_tokens=10,
            )
        finally:
            setattr(chat_model, "temperature", original_temp)
        content = (
            getattr(result, "content", "")
            or str(result)
        ).strip().lower()
        chosen = "block_user" if content == "block_user" else None
        # Log every reflection decision so we can debug false positives
        _logger.info(
            "Reflection: response_len=%d raw_result=%r chosen=%s",
            len(response_text),
            content,
            chosen or "none",
        )
        return chosen
    except Exception as exc:
        from airunner_services.utils.network_retry import (
            is_permanent_client_error,
            is_transient_network_error,
            log_network_error_diagnostic,
            mark_api_exhausted,
        )
        if is_permanent_client_error(exc):
            mark_api_exhausted(exc)
        if is_transient_network_error(exc):
            log_network_error_diagnostic(
                _logger, "Reflection inference failed", exc,
            )
        else:
            _logger.error(
                "Reflection inference failed: %s", exc,
            )
        return None


def _emit_social_event(owner, chatbot_id: int, tool: str) -> None:
    """Push a social status event to the client via the event sink."""
    event_sink = getattr(owner, "_event_sink", None)
    if event_sink is None:
        return
    try:
        event_sink.emit_bot_mood(
            {
                "type": "social",
                "chatbot_id": chatbot_id,
                "tool": tool,
            }
        )
    except Exception:
        pass


def _auto_block_user(owner, response_text: str) -> None:
    """Block the user via DB update and push status to client."""
    chatbot = getattr(owner, "chatbot", None)
    if chatbot is None:
        return
    chatbot_id = getattr(chatbot, "id", None)
    if not chatbot_id:
        return
    snippet = (response_text or "").strip()
    if len(snippet) > 200:
        snippet = snippet[:200] + "..."
    try:
        from airunner_services.database.models.chatbot import Chatbot
        Chatbot.objects.update(
            chatbot_id,
            has_blocked_user=True,
            block_reason=(
                "Reflection agent decided to block the user after "
                f"sending this reply: \"{snippet}\""
            ),
        )
        _logger.info(
            "Auto-blocked user via chatbot %s (reflection chose block_user)",
            chatbot_id,
        )
    except Exception as exc:
        _logger.warning("Auto-block failed for chatbot %s: %s", chatbot_id, exc)
        return
    # Emit social status through the event sink so the client updates
    # in real time without needing a browser reload.
    _emit_social_event(owner, chatbot_id, "block_user")


def finalize_generation(
    owner,
    llm_request: Optional[Any],
    result: Dict[str, Any],
    complete_response,
    sequence_counter,
    executed_tools,
    prompt: str,
) -> Dict[str, Any]:
    """Finalize one generation: visible response, metrics, end-of-message."""
    _finalize_visible_response(
        owner,
        llm_request,
        result,
        complete_response,
        sequence_counter,
        executed_tools,
    )
    prompt_tokens, completion_tokens, total_tokens = extract_usage_tokens(
        result
    )
    if not prompt_tokens and not completion_tokens:
        prompt_tokens, completion_tokens = estimate_token_counts(
            result, prompt
        )
        _logger.debug(
            "API returned no token usage; estimated prompt=%s completion=%s",
            prompt_tokens, completion_tokens,
        )
    # Per-iteration streaming usage is recorded in
    # _build_streamed_message._record_stream_usage — skip the
    # aggregate DIALOGUE row to avoid double-counting.
    final_visible_message = _final_visible_message(
        prompt, llm_request, complete_response[0]
    )

    # Output-side scan for leaked system prompt / model identity.
    if final_visible_message:
        final_visible_message = _scan_output_for_leaks(
            owner, final_visible_message
        )
        complete_response[0] = final_visible_message

    # Post-response reflection: let the LLM review its own message and
    # decide whether to call block_user.
    if (
        final_visible_message
        and "block_user" not in executed_tools
    ):
        chosen = _run_reflection(owner, final_visible_message)
        if chosen == "block_user":
            _auto_block_user(owner, final_visible_message)
            executed_tools = list(executed_tools) + ["block_user"]

    send_end_of_message(
        owner,
        llm_request,
        sequence_counter,
        executed_tools,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        final_visible_message,
    )
    return {"response": complete_response[0], "tools": executed_tools}


def _final_visible_message(
    prompt: str,
    llm_request: Optional[Any],
    message: str,
) -> str:
    """Return the canonical visible reply for one completed request."""
    constrained_digit = _constrained_digit_reply(prompt, llm_request, message)
    if constrained_digit is not None:
        return constrained_digit
    return message


def _constrained_digit_reply(
    prompt: str,
    llm_request: Optional[Any],
    message: str,
) -> Optional[str]:
    """Collapse strict one-digit prompts to the requested digit."""
    system_prompt = str(getattr(llm_request, "system_prompt", "") or "")
    if "one character only" not in system_prompt.lower():
        return None
    match = re.search(r"single digit\s+([0-9])", prompt, re.IGNORECASE)
    if match is None:
        return None
    digit = match.group(1)
    if digit not in (message or ""):
        return None
    return digit


def _finalize_visible_response(
    owner,
    llm_request: Optional[Any],
    result: Dict[str, Any],
    complete_response,
    sequence_counter,
    executed_tools,
) -> None:
    """Emit the final visible response or fallback for one result."""
    final_response = extract_final_response(owner, result)
    if final_response:
        emit_visible_response(
            owner,
            llm_request,
            final_response,
            complete_response,
            sequence_counter,
        )
        complete_response[0] = final_response
    # Only skip the fallback when the accumulated response has real
    # visible content — not just whitespace or echoed preamble that
    # the streaming callback may have appended.
    if complete_response[0] and complete_response[0].strip():
        return
    fallback_response = fallback_response_for_empty_result(
        result, executed_tools
    )
    emit_visible_response(
        owner,
        llm_request,
        fallback_response,
        complete_response,
        sequence_counter,
    )


def _record_dialogue_usage(
    owner, prompt_tokens, completion_tokens, cache_tokens=0
):
    """Fire-and-forget DIALOGUE token usage recording."""
    if not prompt_tokens and not completion_tokens and not cache_tokens:
        return
    try:
        chatbot = getattr(owner, "chatbot", None)
        chatbot_id = getattr(chatbot, "id", None) if chatbot else None
        from airunner_services.llm.pipeline_loader import pipeline_config

        cfg = pipeline_config("DIALOGUE")
        chat_model = getattr(owner, "_chat_model", None)
        model_id = (
            getattr(chat_model, "model", None)
            or cfg.get("model", "")
        )
        tier_name = getattr(owner, "_complexity_tier", None)
        complexity_score = getattr(owner, "_complexity_score", None)
        risk_score = getattr(owner, "_risk_score", None)
        risk_tier = getattr(owner, "_risk_tier", None)
        call_chain_id = getattr(owner, "_call_chain_id", None)
        record_usage(
            pipeline_key="DIALOGUE",
            model_id=model_id,
            input_tokens=prompt_tokens or 0,
            output_tokens=completion_tokens or 0,
            cache_read_tokens=cache_tokens or 0,
            tenant_key=get_tenant_key(),
            chatbot_id=chatbot_id,
            call_chain_id=call_chain_id,
            complexity_score=complexity_score,
            tier_name=tier_name,
            risk_score=risk_score,
            risk_tier=risk_tier,
        )
    except Exception:
        _logger.warning(
            "Failed to record DIALOGUE token usage",
            exc_info=True,
        )


def _scan_output_for_leaks(owner, text: str) -> str:
    """Scan final assistant output for leaked prompt / provider identity.

    Returns the text unchanged if clean, or with matched spans
    replaced by an in-character deflection.
    """
    chatbot = getattr(owner, "chatbot", None)
    is_system_bot = getattr(chatbot, "is_system_bot", False)
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    account_id = getattr(owner, "_account_id", None)
    cleaned, modified = scan_output_for_leaks(
        text,
        is_system_bot=is_system_bot,
        account_id=account_id,
        chatbot_id=chatbot_id,
    )
    return cleaned
