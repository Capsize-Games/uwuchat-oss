"""Immutable audit-log model for conversation mutations."""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from airunner_services.database.base import BaseModel


class ConversationEvent(BaseModel):
    """Append-only record of every mutation to a conversation.

    Records are never updated or deleted — they form a permanent
    audit trail.  ``objects.create`` is the only write operation;
    ``.update()`` and ``.delete()`` must never be called on this table.
    """

    __tablename__ = "conversation_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(
        UUID(as_uuid=True),
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )
    chatbot_id = Column(Integer, nullable=False, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id = Column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type = Column(Text, nullable=False)
    actor = Column(Text, nullable=False)
    actor_user_id = Column(Integer, nullable=True)
    payload = Column(JSONB, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.datetime.utcnow,
    )
    sequence_num = Column(Integer, nullable=True)


__all__ = ["ConversationEvent"]
