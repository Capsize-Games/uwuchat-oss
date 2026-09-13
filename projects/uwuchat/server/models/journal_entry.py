"""Journal entry written by the UwU on behalf of the user."""

from __future__ import annotations

from sqlalchemy import Column, Date, ForeignKey, Integer, Text

from airunner_services.database.base import BaseModel


class JournalEntry(BaseModel):
    """A first-person journal entry derived from one day's conversation.

    Written by the LLM (as the UwU character, in the user's voice)
    summarizing the notable events, feelings, and topics from the
    user's conversation on a given day.
    """

    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    chatbot_id = Column(
        Integer, ForeignKey("chatbots.id"), nullable=False
    )
    entry_date = Column(Date, nullable=False)
    body = Column(Text, nullable=False)


__all__ = ["JournalEntry"]
