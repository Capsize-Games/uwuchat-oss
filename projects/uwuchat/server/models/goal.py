"""Goal model and GoalStatus enum."""

from __future__ import annotations

from enum import Enum

from sqlalchemy import Column, Date, ForeignKey, Integer, String, Text

from airunner_services.database.base import BaseModel


class GoalStatus(str, Enum):
    """Lifecycle states for a user goal."""

    ACTIVE = "active"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"


class Goal(BaseModel):
    """A long-term personal goal the user is working toward.

    Tasks can optionally be linked to a goal via goal_id.
    """

    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    target_date = Column(Date, nullable=True)
    status = Column(
        String(32), nullable=False, default=GoalStatus.ACTIVE.value
    )


__all__ = ["Goal", "GoalStatus"]
