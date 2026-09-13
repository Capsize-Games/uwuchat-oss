"""EmailBodyChunk — one embedded, per-user-encrypted chunk of an email
thread's real message content.

The ``embedding_enc`` column stores a CKKS-encrypted embedding vector
(serialized ``tenseal.CKKSVector``).  The former plaintext pgvector
``embedding`` column has been removed to close the embedding-inversion
leak — the same class of fix already applied to ``KnowledgeFact`` and
``ConversationTurn``.
"""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)

from airunner_services.database.base import BaseModel
from airunner_services.utils.crypto import UserEncryptedText


class EmailBodyChunk(BaseModel):
    """One chunk of a thread's concatenated message bodies.

    ``content_ciphertext`` is encrypted via the per-user DEK pattern
    (same approach as ``KnowledgeFact.fact_text``).
    ``embedding_enc`` is a CKKS ciphertext — the secret key is
    per-account, DEK-wrapped, and never persisted in the clear.
    """

    __tablename__ = "email_body_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_account_id = Column(Integer, nullable=False, index=True)
    thread_id = Column(String(255), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False, default=0)
    content_ciphertext = Column(UserEncryptedText, nullable=False)
    embedding_enc = Column(LargeBinary, nullable=True)
    participant_count = Column(Integer, nullable=False, default=0)
    message_count = Column(Integer, nullable=False, default=0)
    date_range_start = Column(DateTime, nullable=True)
    date_range_end = Column(DateTime, nullable=True)
    generated_at = Column(DateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "email_account_id", "thread_id", "chunk_index",
            name="uq_email_body_chunks_thread_idx",
        ),
    )


__all__ = ["EmailBodyChunk"]
