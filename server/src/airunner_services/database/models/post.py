"""Post model — UwU social posts with lazy content generation."""

from __future__ import annotations

import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from airunner_services.database.base import BaseModel


class Post(BaseModel):
    """A social post made by a chatbot; content generated lazily on first read."""

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chatbot_id = Column(
        Integer, ForeignKey("chatbots.id"), nullable=False, index=True
    )
    content = Column(Text, nullable=True)
    context_snapshot = Column(JSONB, nullable=True)
    visibility = Column(String(16), nullable=False, default="public")
    created_at = Column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    generated_at = Column(DateTime, nullable=True)


__all__ = ["Post"]
