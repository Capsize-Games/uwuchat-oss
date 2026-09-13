"""Relationship model — tracks how a chatbot relates to users and other bots."""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)

from airunner_services.database.base import BaseModel


class Relationship(BaseModel):
    """Per-chatbot relationship record with a user or another chatbot."""

    __tablename__ = "relationships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chatbot_id = Column(
        Integer, ForeignKey("chatbots.id"), nullable=False, index=True
    )
    target_type = Column(String(16), nullable=False)
    target_id = Column(Integer, nullable=False)
    warmth = Column(Float, default=0.5, nullable=False)
    trust = Column(Float, default=0.5, nullable=False)
    dynamic = Column(String(64), nullable=True)
    private_thoughts = Column(Text, nullable=True)
    last_interaction_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )


__all__ = ["Relationship"]
