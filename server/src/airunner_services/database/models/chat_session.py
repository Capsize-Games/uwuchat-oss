"""Session model — one time-bounded slice of a persistent UwU thread.

A new session is created automatically when the gap between messages exceeds
SESSION_GAP_HOURS (4 h).  Sessions are invisible to the user; from their
perspective there is one continuous thread per UwU.

After a session goes cold, a background job generates an episodic summary
(episodic_summary / summary_ready) that is injected into future prompts so
the UwU retains a narrative memory of past conversations.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB

from airunner_services.database.base import BaseModel

SESSION_GAP_HOURS = 4


class ChatSession(BaseModel):
    """One time-bounded session within a persistent UwU conversation thread."""

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chatbot_id = Column(
        Integer, ForeignKey("chatbots.id"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    started_at = Column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    last_message_at = Column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    episodic_summary = Column(Text, nullable=True)
    rolling_summary = Column(Text, nullable=True)
    emotional_weight = Column(Float, nullable=True)
    key_topics = Column(JSONB, nullable=True)
    summary_ready = Column(Boolean, default=False, nullable=False)


__all__ = ["ChatSession", "SESSION_GAP_HOURS"]
