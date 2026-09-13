"""Knowledge extraction / interjection / curiosity Celery tasks.

These are Tier-2 tasks: they touch DEK-encrypted data and require
the DEK relay.  The caller must write the wrapped DEK into the relay
before enqueuing.

The task bodies contain the actual extraction/interjection logic
moved from ``knowledge_extractor.py`` and ``interjection_engine.py``.
"""

from __future__ import annotations


from celery.utils.log import get_task_logger

from airunner_services.tasks.celery_app import app

from airunner_services.conf.model_settings import META_LLAMA_INSTRUCT_MODEL

logger = get_task_logger(__name__)


@app.task(
    bind=True,
    name=(
        "airunner_services.tasks.knowledge_tasks.extract_knowledge"
    ),
    queue="default",
    max_retries=1,
)
def extract_knowledge(
    self,
    tenant_key: str,
    account_id: int,
    chatbot_id: int,
    user_text: str,
    assistant_text: str,
    conversation_id: int,
    call_chain_id: str,
    grounding_sources: str = "",
) -> dict:
    """Run knowledge extraction on a conversation turn.

    Tier-2: touches ``KnowledgeFact.fact_text`` (DEK-encrypted).
    Receives ``chatbot_id``, ``user_text``, ``assistant_text`` etc.
    explicitly — contextvars do not cross the Celery broker boundary.
    Reconstructs the chat model from pipeline config rather than
    receiving a Python object that cannot be serialized.

    *grounding_sources*: newline-joined search/tool result text from
    the current turn, passed so the extractor can evaluate grounding
    for ``subject="world"`` facts across the Celery boundary.
    """
    from airunner_services.tasks.task_helpers import task_dek_scope

    logger.info(
        "Knowledge extraction: tenant=%s account=%d conv=%d",
        tenant_key, account_id, conversation_id,
    )
    with task_dek_scope(tenant_key, account_id) as dek:
        if dek is None:
            logger.info(
                "DEK relay empty for account %d — "
                "skipping knowledge extraction",
                account_id,
            )
            return {"status": "skipped", "reason": "no_dek"}

        chat_model = _resolve_extractor_chat_model()
        if chat_model is None:
            logger.warning(
                "No chat model for KNOWLEDGE stage — skipping"
            )
            return {"status": "skipped", "reason": "no_chat_model"}

        from airunner_services.llm.knowledge_extractor import (
            _invoke_with_retry,
            _make_extractor_tools,
        )

        model_label = getattr(
            chat_model, "model_name", chat_model,
        )
        logger.info(
            "[EXTRACTOR] model: %s", model_label,
        )

        try:
            tools, tools_map = _make_extractor_tools(chatbot_id)
            bound = chat_model.bind_tools(tools)
            _invoke_with_retry(
                chatbot_id, user_text, assistant_text, bound,
                tools_map, conversation_id, call_chain_id,
                grounding_sources=grounding_sources,
            )
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
                    logger, "[EXTRACTOR] Network failure", exc,
                )
            else:
                logger.error("[EXTRACTOR] Failed: %s", exc)

    return {"status": "complete"}


@app.task(
    bind=True,
    name=(
        "airunner_services.tasks.knowledge_tasks.run_interjection"
    ),
    queue="default",
    max_retries=1,
)
def run_interjection(
    self,
    tenant_key: str,
    account_id: int,
    chatbot_id: int,
) -> dict:
    """Run interjection engine for a chatbot.

    Tier-2: touches ``Conversation.value``/``.summary``
    (DEK-encrypted).  Reconstructs the chat model from config.
    The ``countdown`` on the enqueue call handles the delay.
    """
    from airunner_services.tasks.task_helpers import task_dek_scope

    logger.info(
        "Interjection: tenant=%s account=%d bot=%d",
        tenant_key, account_id, chatbot_id,
    )
    with task_dek_scope(tenant_key, account_id) as dek:
        if dek is None:
            logger.info(
                "DEK relay empty for account %d — "
                "skipping interjection",
                account_id,
            )
            return {"status": "skipped", "reason": "no_dek"}

        chat_model = _resolve_interjection_chat_model()
        if chat_model is None:
            logger.warning(
                "No chat model for interjection — skipping"
            )
            return {"status": "skipped", "reason": "no_chat_model"}

        from airunner_services.llm.interjection_engine import (
            _generate_and_persist,
        )

        try:
            _generate_and_persist(chatbot_id, chat_model, account_id)
        except Exception:
            logger.exception(
                "Interjection failed for chatbot %s", chatbot_id,
            )

    return {"status": "complete"}


@app.task(
    bind=True,
    name=(
        "airunner_services.tasks.knowledge_tasks.run_curiosity"
    ),
    queue="default",
    max_retries=1,
)
def run_curiosity(
    self,
    tenant_key: str,
    account_id: int,
    chatbot_id: int,
    user_text: str,
    assistant_text: str,
) -> dict:
    """Run curiosity engine on a conversation.

    Tier 1 per audit, but passes DEK for forward compatibility.
    Currently retired (no-op in ``generation_execution_support.py``).
    """
    from airunner_services.tasks.task_helpers import task_dek_scope

    logger.info(
        "Curiosity: tenant=%s account=%d bot=%d",
        tenant_key, account_id, chatbot_id,
    )
    with task_dek_scope(tenant_key, account_id) as dek:
        if dek is None:
            logger.info(
                "DEK relay empty for account %d — "
                "skipping curiosity",
                account_id,
            )
            return {"status": "skipped", "reason": "no_dek"}

        chat_model = _resolve_interjection_chat_model()
        if chat_model is None:
            return {"status": "skipped", "reason": "no_chat_model"}

        from airunner_services.llm.curiosity_engine import (
            _call_model,
            _load_facts,
            _upsert_question,
        )

        try:
            fact_lines = _load_facts(chatbot_id)
            data = _call_model(
                chat_model, user_text, assistant_text, fact_lines,
            )
            if data:
                _upsert_question(chatbot_id, **data)
        except Exception as exc:
            logger.warning("[CURIOSITY] Failed: %s", exc)

    return {"status": "complete"}


# -- Chat model reconstruction helpers --------------------------------------


def _resolve_extractor_chat_model():
    """Reconstruct the chat model for the KNOWLEDGE stage.

    Uses ``create_openrouter_model`` with pipeline config to build
    a fresh ``ChatOpenAI`` instance inside the Celery worker.  The
    original in-process approach passed a pre-built LangChain model
    object, which cannot cross the Celery broker boundary.
    """
    import os

    from airunner_services.cloud.llm.model_builders import (
        create_openrouter_model,
    )
    from airunner_services.llm.pipeline_loader import (
        pipeline_config,
    )

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    cfg = pipeline_config("KNOWLEDGE")
    return create_openrouter_model(
        api_key=api_key,
        model_name=cfg.get(
            "model", META_LLAMA_INSTRUCT_MODEL,
        ),
        temperature=cfg.get("temperature", 0.3),
        max_tokens=cfg.get("max_tokens", 500),
    )


def _resolve_interjection_chat_model():
    """Reconstruct the chat model for interjection/curiosity.

    Same reconstruction approach as the extractor.
    """
    import os

    from airunner_services.cloud.llm.model_builders import (
        create_openrouter_model,
    )
    from airunner_services.llm.pipeline_loader import (
        pipeline_config,
    )

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    cfg = pipeline_config("INTERJECTION")
    return create_openrouter_model(
        api_key=api_key,
        model_name=cfg.get(
            "model", cfg.get(
                "model", META_LLAMA_INSTRUCT_MODEL,
            ),
        ),
        temperature=cfg.get("temperature", 0.7),
        max_tokens=cfg.get("max_tokens", 200),
    )
