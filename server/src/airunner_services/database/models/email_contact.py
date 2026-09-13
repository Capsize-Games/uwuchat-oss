"""EmailContact — people the user emails with, enriched by Level-2 LLM."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from airunner_services.database.base import BaseModel
from airunner_services.utils.crypto import UserEncryptedText


class EmailContact(BaseModel):
    """One contact derived from email headers and enriched by LLM.

    Header-level counts (message_count_from/to, first/last_seen) are
    populated during Phase 2 preprocessing without any LLM call.
    ``relationship_note_ciphertext`` is a short LLM-inferred description
    written by Phase 4 and encrypted via the per-user DEK pattern.
    """

    __tablename__ = "email_contacts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    email_address = Column(String(255), nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    first_seen_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    message_count_from = Column(Integer, nullable=False, default=0)
    message_count_to = Column(Integer, nullable=False, default=0)
    avg_response_time_seconds = Column(Integer, nullable=True)
    relationship_note_ciphertext = Column(
        UserEncryptedText, nullable=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "email_address",
            name="uq_email_contacts_user_email",
        ),
    )


__all__ = ["EmailContact"]
