"""Entity — one real-world thing the system has learned about.

A generic type-discriminated table: person, place, thing, concept,
organization, event.  Scoped per chatbot_id so different chatbots can
learn about the same real entity independently.

``email_contacts`` is a source-specific staging table — this is the
cross-source, LLM-facing identity.  ``display_name_ct`` and
``aliases_ct`` are encrypted via the per-user DEK pattern.
``name_lookup_hash`` is a deterministic HMAC blind index for fast
exact-match lookups during resolution.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, String

from airunner_services.database.base import BaseModel
from airunner_services.utils.crypto import UserEncryptedText


class Entity(BaseModel):
    """One real-world entity scoped to one chatbot's knowledge graph."""

    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(
        String(32), nullable=False, default="person",
    )
    chatbot_id = Column(Integer, nullable=True, index=True)
    display_name_ct = Column(UserEncryptedText, nullable=False)
    name_lookup_hash = Column(String(64), nullable=False, index=True)
    aliases_ct = Column(UserEncryptedText, nullable=True)
    source_type = Column(
        String(32), nullable=False, default="inferred",
    )
    source_ref_table = Column(String(64), nullable=True)
    source_ref_id = Column(Integer, nullable=True)


__all__ = ["Entity"]
