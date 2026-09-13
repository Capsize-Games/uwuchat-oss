"""Level-2 LLM: fact extraction from email body chunks (Phase 4).

Consumes indexed email body content (``EmailBodyChunk``). Writes into
``knowledge_facts`` scoped to the system bot with
``data_source='email'``.  Contact enrichment lives in
``contact_enrichment.py``.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Optional

from airunner_services.database.models.chatbot import Chatbot
from airunner_services.database.models.email_body_chunk import (
    EmailBodyChunk,
)
from airunner_services.database.session import session_scope
from airunner_services.knowledge_context import (
    set_knowledge_chatbot_id,
    set_knowledge_subject,
)

from airunner_services.conf.model_settings import CLAUDE_HAIKU_MODEL

logger = logging.getLogger(__name__)

# Cap per-thread concatenation before feeding it to fact extraction —
# email bodies are far longer than the old one-sentence summaries, and
# an unbounded concatenation risks blowing the extraction model's
# context window.
_MAX_THREAD_CHARS = 8000


def extract_facts_from_email_bodies(
    account_id: int,
    user_id: int,
    since: "datetime.datetime | None" = None,
) -> int:
    """Run fact extraction on email body chunks generated after *since*.

    If *since* is None (first sync), processes all chunks.
    Returns the number of new facts created.
    """
    system_bot_id = _get_system_bot_id()
    if system_bot_id is None:
        logger.warning("No system bot found; skipping fact extraction")
        return 0

    texts = _gather_thread_texts(account_id, since)
    if not texts:
        return 0

    model = _load_knowledge_model()
    if model is None:
        return 0

    total_facts = 0
    for text in texts:
        facts = _extract_facts_from_text(text, model)
        if facts:
            total_facts += len(facts)
            _persist_facts(
                facts, system_bot_id,
                account_id=account_id,
            )

    return total_facts


def _gather_thread_texts(
    account_id: int,
    since: "datetime.datetime | None",
) -> list[str]:
    """Group this account's body chunks by thread, concatenate each
    thread's chunks (in order) up to _MAX_THREAD_CHARS, and return one
    text blob per thread."""
    with session_scope() as session:
        q = session.query(EmailBodyChunk).filter(
            EmailBodyChunk.email_account_id == account_id,
        )
        if since is not None:
            q = q.filter(EmailBodyChunk.generated_at > since)
        chunks = q.order_by(EmailBodyChunk.chunk_index).all()

        by_thread: dict[str, list[str]] = {}
        for chunk in chunks:
            text = chunk.content_ciphertext
            if text and isinstance(text, str):
                by_thread.setdefault(chunk.thread_id, []).append(text)

    texts = []
    for chunk_texts in by_thread.values():
        combined = "\n\n".join(chunk_texts)[:_MAX_THREAD_CHARS]
        if combined:
            texts.append(combined)
    return texts


def _extract_facts_from_text(text: str, model) -> list[str]:
    """Extract discrete facts from one thread's concatenated text."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = (
            "Extract discrete personal facts from the following email "
            "thread content. Each fact must be a single, self-contained "
            "declarative statement about the account owner, durable "
            "(not transient), and specific.\n\n"
            "Examples: 'The account owner works in software engineering', "
            "'The account owner is planning a trip in October'.\n\n"
            "Return ONLY a JSON array of strings. If no durable facts, "
            "return []."
        )
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=text),
        ]
        response = model.invoke(messages)
        raw = str(getattr(response, "content", response) or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            return json.loads(raw)
        return []
    except Exception as exc:
        logger.warning("Fact extraction failed: %s", exc)
        return []


def _persist_facts(
    facts: list[str],
    system_bot_id: int,
    account_id: "int | None" = None,
) -> None:
    """Write extracted facts to knowledge_facts, scoped to system bot.

    Args:
        facts: Extracted fact strings to persist.
        system_bot_id: Chatbot ID to scope facts under.
        account_id: Account ID for cost-tracking attribution on the
            embedding call made inside ``add_fact``.
    """
    from airunner_services.knowledge import get_knowledge_base

    kb = get_knowledge_base()
    set_knowledge_chatbot_id(system_bot_id)
    set_knowledge_subject("user")

    for fact_text in facts:
        fact_text = fact_text.strip()
        if not fact_text:
            continue
        try:
            kb.add_fact(
                fact_text,
                source_type="inferred",
                data_source="email",
                account_id=account_id,
            )
        except Exception as exc:
            logger.debug("Failed to persist fact: %s", exc)


def _get_system_bot_id() -> Optional[int]:
    """Return the stable chatbot ID for the system bot in this tenant."""
    with session_scope() as session:
        bot = (
            session.query(Chatbot)
            .filter(Chatbot.is_system_bot.is_(True))
            .first()
        )
        return bot.id if bot else None


def _load_knowledge_model():
    """Load the KNOWLEDGE model from the UwUchat pipeline config."""
    try:
        import os

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            return None

        from airunner_services.cloud.llm.model_builders import (
            create_openrouter_model,
        )
        from airunner_services.llm.pipeline_loader import pipeline_config

        cfg = pipeline_config("KNOWLEDGE")
        return create_openrouter_model(
            api_key=api_key,
            model_name=cfg.get(
                "model", CLAUDE_HAIKU_MODEL,
            ),
            temperature=cfg.get("temperature", 0.3),
            max_tokens=cfg.get("max_tokens", 1024),
        )
    except Exception as exc:
        logger.warning("Failed to load knowledge model: %s", exc)
        return None
