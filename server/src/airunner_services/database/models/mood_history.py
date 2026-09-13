"""Per-turn mood history for chatbot emotional state tracking."""

from sqlalchemy import Column, Float, Integer, String, Text

from airunner_services.database.base import BaseModel


class MoodHistory(BaseModel):
    """One mood-state entry recorded per conversation turn."""

    __tablename__ = "mood_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chatbot_id = Column(Integer, nullable=True, index=True)
    conversation_id = Column(Integer, nullable=True, index=True)
    mood = Column(String(64), nullable=False, default="neutral")
    emoji = Column(String(16), nullable=False, default="😐")
    reason = Column(Text, nullable=True)
    intensity = Column(Float, nullable=False, default=1.0)


__all__ = ["MoodHistory"]
