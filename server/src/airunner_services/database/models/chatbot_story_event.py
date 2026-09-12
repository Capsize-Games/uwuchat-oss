"""Chatbot story event model — discrete narrative beats in world state."""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String

from airunner_services.database.base import BaseModel


class ChatbotStoryEvent(BaseModel):
    """One story event that occurred in a chatbot's world.

    Story events are discrete narrative beats (item found, encounter, illness,
    milestone, etc.) that happen semi-randomly, driven by world state
    thresholds and elapsed time. They are not messages — they are world-state
    mutations that the chatbot then references in conversation.
    """

    __tablename__ = "chatbot_story_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chatbot_id = Column(
        Integer, ForeignKey("chatbots.id"), nullable=False, index=True
    )
    event_type = Column(String, nullable=False)
    payload = Column(JSON, nullable=True)
    occurred_at = Column(
        DateTime(timezone=True), nullable=False
    )
    surfaced = Column(Boolean, nullable=False, default=False)


__all__ = ["ChatbotStoryEvent"]
