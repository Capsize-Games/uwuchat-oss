"""Headlesscode session model and status enum."""

from __future__ import annotations

from enum import Enum

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
)

from airunner_services.database.base import BaseModel


class HeadlesscodeSessionStatus(str, Enum):
    """Lifecycle states mirroring AgentRunStatus's state names."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HeadlesscodeSession(BaseModel):
    """One headlesscode session launched from a UwUChat conversation.

    ``headlesscode_session_id`` is the id headlesscode generated at
    ``/api/session/start``; ``event_offset`` is the ``since=`` cursor
    for the next poll of the session's events feed.
    """

    __tablename__ = "headlesscode_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("headlesscode_projects.id"),
        nullable=False, index=True,
    )
    chatbot_id = Column(
        Integer, ForeignKey("chatbots.id"), nullable=True
    )
    conversation_id = Column(
        Integer, ForeignKey("conversations.id"), nullable=True
    )
    headlesscode_session_id = Column(
        String(64), nullable=False, index=True
    )
    status = Column(
        String(32), nullable=False,
        default=HeadlesscodeSessionStatus.PENDING.value,
    )
    task_description = Column(Text, nullable=True)
    mode = Column(String(64), nullable=True)
    event_offset = Column(Integer, nullable=False, default=0)


__all__ = ["HeadlesscodeSession", "HeadlesscodeSessionStatus"]
