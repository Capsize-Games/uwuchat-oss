"""LLM invocation helpers for the mood-update pipeline."""

from __future__ import annotations

import logging
import os

from airunner_services.llm.token_usage import record_background_usage

from airunner_services.conf.model_settings import META_LLAMA_INSTRUCT_MODEL

logger = logging.getLogger(__name__)


def _build_mood_model(api_key: str, cfg: dict):
    """Build the LangChain chat model for mood updates."""
    from airunner_services.cloud.llm.model_builders import (
        create_openrouter_model,
    )
    return create_openrouter_model(
        api_key=api_key,
        model_name=cfg.get(
            "model", META_LLAMA_INSTRUCT_MODEL
        ),
        temperature=cfg.get("temperature", 0.3),
        max_tokens=cfg.get("max_tokens", 60),
    )


def _record_background(
    cfg: dict,
    response,
    prompt: str,
    raw: str,
    call_chain_id: str | None,
    chatbot_id: int | None,
    tenant_key: str,
):
    """Write a background-usage row, return usage_id."""
    return record_background_usage(
        "INTRA_SESSION_MOOD", cfg, response,
        chatbot_id=chatbot_id, tenant_key=tenant_key,
        call_chain_id=call_chain_id,
        prompt_char_count=len(prompt) if prompt else None,
        response_char_count=len(raw) if raw else None,
    )


def _record_pipeline_text(
    usage_id, tenant_key: str, prompt: str, raw: str,
) -> None:
    """Record the full prompt and response text for inspection."""
    from airunner_services.llm.token_usage import (
        record_pipeline_call_text,
    )
    record_pipeline_call_text(
        usage_id=usage_id,
        tenant_key=tenant_key,
        prompt_text=prompt,
        response_text=raw,
    )


def _record_mood_usage(
    cfg: dict,
    response,
    prompt: str,
    raw: str,
    call_chain_id: str | None,
    chatbot_id: int | None,
) -> None:
    """Record token usage and prompt/response text for a mood call."""
    from airunner_services.data.tenant import get_tenant_key

    tenant_key = get_tenant_key()
    usage_id = _record_background(
        cfg, response, prompt, raw,
        call_chain_id, chatbot_id, tenant_key,
    )
    _record_pipeline_text(usage_id, tenant_key, prompt, raw)


def _log_llm_failure(exc: Exception) -> None:
    """Log an LLM call failure at the appropriate level."""
    from airunner_services.utils.network_retry import (
        is_transient_network_error,
        log_network_failure,
    )
    if is_transient_network_error(exc):
        log_network_failure(
            logger, "Mood update LLM call failed", exc
        )
    else:
        logger.error(
            "Mood update LLM call failed", exc_info=True
        )


def _invoke_llm(api_key: str, cfg: dict, prompt: str):
    """Build model, invoke, return (raw_text, response) tuple."""
    model = _build_mood_model(api_key, cfg)
    from langchain_core.messages import HumanMessage
    from airunner_services.cloud.llm.completion_choke import (
        invoke_with_limiter,
    )

    response = invoke_with_limiter(
        model,
        [HumanMessage(content=prompt)],
        priority="bulk",
    )
    text = str(getattr(response, "content", response) or "").strip()
    return text, response


def _call_llm(
    prompt: str,
    call_chain_id: str | None = None,
    chatbot_id: int | None = None,
) -> str:
    """Call the configured cloud LLM for mood update."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return ""
    from airunner_services.llm.pipeline_loader import pipeline_config

    cfg = pipeline_config("INTRA_SESSION_MOOD")
    try:
        raw, response = _invoke_llm(api_key, cfg, prompt)
        _record_mood_usage(cfg, response, prompt, raw,
                           call_chain_id, chatbot_id)
        return raw
    except Exception as exc:
        _log_llm_failure(exc)
        return ""
