"""Durable headlesscode session event transcript."""

from __future__ import annotations

from sqlalchemy import JSON, Column, ForeignKey, Integer, String

from airunner_services.database.base import BaseModel


class HeadlesscodeSessionEvent(BaseModel):
    """One verbatim event from a headlesscode session's events feed.

    ``raw_event`` stores the raw headlesscode event payload;
    ``chat_block_kind`` is the ``turn``/``system`` grouping from
    ``groupEventsIntoChat``.
    """

    __tablename__ = "headlesscode_session_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(
        Integer, ForeignKey("headlesscode_sessions.id"),
        nullable=False, index=True,
    )
    raw_event = Column(JSON, nullable=False)
    chat_block_kind = Column(String(16), nullable=True)


__all__ = ["HeadlesscodeSessionEvent"]
