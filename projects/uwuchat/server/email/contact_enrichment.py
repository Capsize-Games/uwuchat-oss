"""Level-2 LLM: contact relationship-note generation (Phase 4).

Split from extractor.py to keep files under 250 lines.
"""

from __future__ import annotations

import logging
from typing import Optional

from airunner_services.database.models.email_contact import EmailContact
from airunner_services.database.session import session_scope

from airunner_services.conf.model_settings import CLAUDE_HAIKU_MODEL

logger = logging.getLogger(__name__)

_MIN_MESSAGES_FOR_RELATIONSHIP = 10


def enrich_contacts(user_id: int) -> int:
    """Generate relationship notes for high-signal contacts.

    Returns the number of contacts enriched.
    """
    with session_scope() as session:
        contacts = (
            session.query(EmailContact)
            .filter(
                EmailContact.user_id == user_id,
                EmailContact.relationship_note_ciphertext.is_(None),
            )
            .all()
        )
        candidates = [
            c for c in contacts
            if (c.message_count_from + c.message_count_to)
            >= _MIN_MESSAGES_FOR_RELATIONSHIP
        ]
        if not candidates:
            return 0

    model = _load_knowledge_model()
    if model is None:
        return 0

    total_enriched = 0
    for contact in candidates:
        note = _generate_relationship_note(contact, model)
        if note:
            _persist_relationship_note(contact.id, note)
            total_enriched += 1

    return total_enriched


def _generate_relationship_note(contact, model) -> Optional[str]:
    """Generate a short relationship description for one contact."""
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = (
            "Based on email contact statistics, write a SHORT one-sentence "
            "description (max 15 words) of this person's likely relationship "
            "to the account owner. Use generic terms: 'a colleague', "
            "'a family member', 'a service provider', etc.\n\n"
            f"Messages received: {contact.message_count_from}\n"
            f"Messages sent: {contact.message_count_to}\n"
            f"First seen: {contact.first_seen_at}\n"
            f"Last seen: {contact.last_seen_at}\n"
        )
        messages = [
            SystemMessage(content="You describe relationships concisely."),
            HumanMessage(content=prompt),
        ]
        response = model.invoke(messages)
        note = str(getattr(response, "content", response) or "").strip()
        return note[:200] if note else None
    except Exception as exc:
        logger.warning("Relationship note generation failed: %s", exc)
        return None


def _persist_relationship_note(contact_id: int, note: str) -> None:
    """Store a relationship note on the contact record."""
    with session_scope() as session:
        contact = session.query(EmailContact).get(contact_id)
        if contact is not None:
            contact.relationship_note_ciphertext = note
            session.commit()


def _load_knowledge_model():
    """Load the KNOWLEDGE extraction model from the UwUchat pipeline."""
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
