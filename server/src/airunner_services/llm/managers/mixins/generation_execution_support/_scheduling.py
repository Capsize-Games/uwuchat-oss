"""Post-generation background task scheduling helpers.

Extracted from ``generation_execution_support``.  Owns the retired
per-turn scheduling no-ops and the deep-research diagnostic logging.
"""

from __future__ import annotations

from airunner_services.contract_enums import LLMActionType


def _maybe_schedule_extraction(
    owner, user_text: str, assistant_text: str
) -> None:
    """Schedule background knowledge extraction if the turn is recordable."""
    from airunner_services.llm.pipeline_loader import is_enabled
    from airunner_services.utils.network_retry import is_api_exhausted

    if not is_enabled("KNOWLEDGE"):
        return
    if getattr(owner, "_turn_failed", False):
        return
    if is_api_exhausted():
        return
    if not assistant_text or not user_text:
        return
    chatbot = getattr(owner, "chatbot", None)
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not chatbot_id:
        return
    conversation_id = _resolve_conversation_id(owner)
    wm = getattr(owner, "_workflow_manager", None)
    chat_model = (
        getattr(owner, "_specialized_chat_models", {}).get("KNOWLEDGE")
        or getattr(owner, "_specialized_chat_models", {}).get("STATELESS")
        or getattr(wm, "_original_chat_model", None)
        or getattr(wm, "_chat_model", None)
    )
    if not chat_model:
        return
    from airunner_services.llm.knowledge_extractor import schedule_extraction
    from airunner_services.data.tenant import (
        get_account_id,
        get_tenant_key,
    )
    from airunner_services.llm.active_call_chain import (
        get_active_call_chain,
    )
    from airunner_services.llm.tools.grounding_tools_helpers import (
        get_grounding_sources,
    )

    call_chain_id = get_active_call_chain()
    schedule_extraction(
        chatbot_id,
        user_text,
        assistant_text,
        chat_model,
        tenant_key=get_tenant_key(),
        conversation_id=conversation_id,
        call_chain_id=call_chain_id,
        account_id=get_account_id(),
        grounding_sources="\n".join(get_grounding_sources()),
    )


def _maybe_schedule_curiosity(
    owner, user_text: str, assistant_text: str, action: "LLMActionType"
) -> None:
    """No-op: curiosity now runs at session-end via summarize_session.

    The per-turn daemon thread path is retired.  CURIOSITY_ENGINE is
    triggered during session rotation (4h+ gap) and seeded from the
    full session arc rather than a single exchange.
    """


def _schedule_mid_session_tasks(owner) -> None:
    """No-op: rolling compression now runs at session-end.

    The per-turn fire-and-forget path is retired.  ROLLING_COMPRESSOR
    compresses the entire cold session during session rotation so the
    episodic summarizer works with a clean, compressed view.
    """


def _log_deep_research_action(owner, action: LLMActionType) -> None:
    """Log diagnostics for deep research mode."""
    if action == LLMActionType.DEEP_RESEARCH:
        owner.logger.info(
            "Deep Research mode - using tool-based research workflow"
        )
        owner.logger.info(
            "Research tools will be used: search_web, search_news, "
            "scrape_website, validate_url, validate_content, and validation tools."
        )


def _resolve_conversation_id(owner) -> "int | None":
    """Return the active conversation_id from the LLM manager's workflow."""
    wm = getattr(owner, "_workflow_manager", None)
    if wm is None:
        return None
    return getattr(wm, "_conversation_id", None)
