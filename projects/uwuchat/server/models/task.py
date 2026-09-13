"""Task model and TaskStatus enum."""

from __future__ import annotations

from enum import Enum

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from airunner_services.database.base import BaseModel


class TaskStatus(str, Enum):
    """Lifecycle states for a tracked task."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ABANDONED = "abandoned"


class Task(BaseModel):
    """A to-do item the UwU is tracking for the user.

    May be free-standing (goal_id NULL) or nested under a Goal.
    The UwU follows up on open/in-progress tasks naturally during
    conversation, guided by the per-turn productivity context.
    """

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    chatbot_id = Column(
        Integer, ForeignKey("chatbots.id"), nullable=True
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(
        String(32), nullable=False, default=TaskStatus.OPEN.value
    )
    goal_id = Column(
        Integer, ForeignKey("goals.id"), nullable=True
    )
    completed_at = Column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["Task", "TaskStatus"]
