"""Pending curiosity question for one chatbot.

One row per chatbot — the engine overwrites it each turn.
The per-turn context injector reads and hard-deletes it before
the next response so the same question is never repeated.
"""

from sqlalchemy import Column, Integer, Text

from airunner_services.database.base import BaseModel


class CuriosityQuestion(BaseModel):
    """One pending curiosity question scoped to one chatbot."""

    __tablename__ = "curiosity_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chatbot_id = Column(Integer, nullable=False, unique=True, index=True)
    entity = Column(Text, nullable=False)
    missing = Column(Text, nullable=False)
    question = Column(Text, nullable=False)


__all__ = ["CuriosityQuestion"]
