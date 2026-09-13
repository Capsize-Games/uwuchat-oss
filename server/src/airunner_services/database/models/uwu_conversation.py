"""UwU-to-UwU conversation — a DM exchange between two chatbots."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, JSON, DateTime

from airunner_services.database.base import BaseModel


class UwuConversation(BaseModel):
    """Stores DM exchanges between two UwU chatbots.

    Messages are stored in the same format as Conversation.value:
    list of {role, content, timestamp, chatbot_id}.
    Role is always "assistant" — both participants are bots.
    """

    __tablename__ = "uwu_conversations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chatbot_a_id = Column(
        Integer, ForeignKey("chatbots.id"), nullable=False, index=True
    )
    chatbot_b_id = Column(
        Integer, ForeignKey("chatbots.id"), nullable=False, index=True
    )
    messages = Column(JSON, nullable=False, default=list)
    last_message_at = Column(DateTime, nullable=True)


__all__ = ["UwuConversation"]
