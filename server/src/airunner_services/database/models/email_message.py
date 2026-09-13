"""EmailMessage — structured metadata for one ingested email (no body)."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from airunner_services.database.base import BaseModel
from airunner_services.utils.crypto import UserEncryptedText


class EmailMessage(BaseModel):
    """Metadata record for one email fetched during sync.

    Raw email bodies are never persisted (privacy decision).  This table
    holds only structured headers + classification flags for later
    retrieval and stats.

    Sender/recipient identities and subject lines are sensitive PII and
    are encrypted at rest via ``UserEncryptedText`` (per-user DEK
    envelope).  ``to_addresses`` and ``cc_addresses`` are JSON lists
    serialized as text before encryption, matching the pattern used for
    ``Conversation.value``.
    """

    __tablename__ = "email_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_account_id = Column(Integer, nullable=False, index=True)
    provider_message_id = Column(String(255), nullable=False, index=True)
    thread_id = Column(String(255), nullable=True, index=True)
    mailbox_role = Column(String(32), nullable=False)
    from_address = Column(UserEncryptedText, nullable=True)
    from_name = Column(UserEncryptedText, nullable=True)
    to_addresses = Column(UserEncryptedText, nullable=True)
    cc_addresses = Column(UserEncryptedText, nullable=True)
    subject = Column(UserEncryptedText, nullable=True)
    sent_at = Column(DateTime, nullable=True, index=True)
    has_attachments = Column(Boolean, nullable=False, default=False)
    is_automated = Column(Boolean, nullable=False, default=False)
    processed_at = Column(DateTime, nullable=True)
    co_occurrence_processed_at = Column(DateTime, nullable=True)


__all__ = ["EmailMessage"]
