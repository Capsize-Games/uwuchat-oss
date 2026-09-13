"""Persist user knowledge facts with FHE-encrypted pgvector embedding.

Each row holds a single fact — recorded, updated, recalled, or soft-deleted
through the KnowledgeBase class in ``airunner_services.knowledge``.
Tags are stored in ``knowledge_tags`` and linked via ``knowledge_fact_tags``.
Soft-deletes use the ``deleted`` flag inherited from BaseModel.

The ``embedding_enc`` column stores a CKKS-encrypted embedding vector
(serialized ``tenseal.CKKSVector``).  The secret key is per-account,
DEK-wrapped, and never persisted in the clear.  See
``airunner_services.utils.crypto.fhe_helpers`` for the encryption
scheme.

Temporal event lifecycle columns (event_date, event_end_date,
event_time, recurring, temporal_status) support structured tracking
of time-bound facts such as deadlines, appointments, and recurring
events.  See ``airunner_services.fact_lifecycle`` for the
deterministic status-transition logic.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Float,
    Index,
    Integer,
    LargeBinary,
    String,
    Time,
)

from airunner_services.database.base import BaseModel
from airunner_services.utils.crypto import UserEncryptedText


class KnowledgeFact(BaseModel):
    """One recorded fact scoped to one chatbot.

    subject='user'  — facts the character knows about the user
    subject='self'  — facts the character knows about itself
    subject='world' — facts about named third parties, places, things,
                      organizations, concepts, or events, or general
                      objective knowledge (not about the user or character)
    """

    __tablename__ = "knowledge_facts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fact_text = Column(UserEncryptedText, nullable=False)
    chatbot_id = Column(Integer, nullable=True, index=True)
    subject = Column(String(16), nullable=False, default="user")
    # FHE-encrypted embedding vector (CKKS ciphertext, serialized).
    # Replaces the former pgvector ``embedding`` column which stored
    # plaintext vectors vulnerable to embedding-inversion attacks.
    embedding_enc = Column(LargeBinary, nullable=True)
    # Structured citation metadata.
    source_type = Column(String(16), nullable=False, default="user_stated")
    source_url = Column(String(512), nullable=True)
    confidence = Column(Float, nullable=True)
    data_source = Column(String(32), nullable=True, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    # Temporal event lifecycle columns.
    event_date = Column(Date, nullable=True)
    event_end_date = Column(Date, nullable=True)
    event_time = Column(Time, nullable=True)
    recurring = Column(Boolean, nullable=False, default=False)
    temporal_status = Column(
        String(16), nullable=False, default="durable"
    )

    __table_args__ = (
        Index("ix_knowledge_facts_chatbot_subject", "chatbot_id", "subject"),
    )


__all__ = ["KnowledgeFact"]
