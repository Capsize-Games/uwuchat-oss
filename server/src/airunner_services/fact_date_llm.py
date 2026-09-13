"""Shared LLM invocation for fact date classification.

Called by ``fact_date_extractor.py`` Stage A and Stage B.  Follows
the same pattern as ``_try_cloud_llm`` in ``episodic_summarizer.py``.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def call_classification_llm(prompt: str) -> str:
    """Invoke the TOOL_CLASSIFICATION tier model for a prompt.

    Returns the model's text response, or "" on failure.
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        logger.warning(
            "No OPENROUTER_API_KEY — skipping date classification"
        )
        return ""

    try:
        from langchain_core.messages import HumanMessage
        from airunner_services.cloud.llm.model_builders import (
            create_openrouter_model,
        )
        from airunner_services.cloud.llm.completion_choke import (
            invoke_with_limiter,
        )
        from airunner_services.llm.pipeline_loader import (
            pipeline_config,
        )

        cfg = pipeline_config("TOOL_CLASSIFICATION")
        model = create_openrouter_model(
            api_key=api_key,
            model_name=str(cfg.get("model", "")),
            temperature=cfg.get("temperature", 0.0),
            max_tokens=cfg.get("max_tokens", 256),
        )
        response = invoke_with_limiter(
            model,
            [HumanMessage(content=prompt)],
            priority="bulk",
        )
        text = str(
            getattr(response, "content", response) or ""
        ).strip()

        _record_usage(cfg, response, prompt, text)
        return text
    except Exception as exc:
        logger.warning(
            "Date classification LLM call failed: %s", exc
        )
        return ""


def _record_usage(
    cfg: dict,
    response,
    prompt: str,
    text: str,
) -> None:
    """Record token usage for cost tracking.  Never raises."""
    try:
        from airunner_services.data.tenant import get_tenant_key
        from airunner_services.llm.token_usage import (
            record_background_usage,
            record_pipeline_call_text,
        )

        usage_id = record_background_usage(
            "TOOL_CLASSIFICATION",
            cfg,
            response,
            tenant_key=get_tenant_key(),
            prompt_char_count=len(prompt),
            response_char_count=len(text),
        )
        if usage_id is not None:
            record_pipeline_call_text(
                usage_id=usage_id,
                tenant_key=get_tenant_key(),
                prompt_text=prompt,
                response_text=text,
            )
    except Exception:
        logger.debug(
            "Cost tracking for date classification failed",
            exc_info=True,
        )
