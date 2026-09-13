"""Calendar event created by the user or the UwU."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)

from airunner_services.database.base import BaseModel


class CalendarEvent(BaseModel):
    """A calendar entry — appointment, reminder, or event.

    May be created by the UwU via tool call (chatbot_id set) or
    synced from an external calendar (chatbot_id NULL).  Optionally
    linked to a Google Calendar event for bidirectional sync.
    """

    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    chatbot_id = Column(
        Integer, ForeignKey("chatbots.id"), nullable=True
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    starts_at = Column(
        DateTime(timezone=True), nullable=False
    )
    ends_at = Column(
        DateTime(timezone=True), nullable=True
    )
    all_day = Column(Boolean, nullable=False, default=False)
    recurrence_rule = Column(String(255), nullable=True)
    google_event_id = Column(String(255), nullable=True)
    reminder_minutes = Column(Integer, nullable=True)
    is_recurring_reminder = Column(
        Boolean, nullable=False, default=False
    )
    recurrence_days = Column(
        String(255), nullable=True
    )


__all__ = ["CalendarEvent"]
