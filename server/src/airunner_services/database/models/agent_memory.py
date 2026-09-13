"""Rolling cumulative memory per chatbot.

After every session is summarized, this document is updated by an LLM
that blends the new session summary with the existing record.  The result
is a single, evolving narrative that captures who the user is, what the
two have experienced together, and how the character has grown — without
growing unboundedly long.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer

from airunner_services.database.base import BaseModel
from airunner_services.utils.crypto import UserEncryptedText


class AgentMemory(BaseModel):
    """One evolving memory document per chatbot."""

    __tablename__ = "agent_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chatbot_id = Column(
        Integer,
        ForeignKey("chatbots.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    summary = Column(UserEncryptedText, nullable=False, default="")
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
    )


__all__ = ["AgentMemory"]
