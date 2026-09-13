"""Individual conversation turns indexed for retrospective search.

Turns from cold sessions are written here so the LLM can search past
conversations by topic or keyword via the recall_conversation tool —
the same way recall_knowledge searches stored facts.

The ``embedding_enc`` column stores a CKKS-encrypted embedding vector
(serialized ``tenseal.CKKSVector``).  The former plaintext pgvector
``embedding`` column has been removed to close the embedding-inversion
leak — the same class of fix already applied to ``KnowledgeFact``.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
)

from airunner_services.database.base import BaseModel
from airunner_services.utils.crypto import UserEncryptedText


class ConversationTurn(BaseModel):
    """One persisted message turn, scoped to a chatbot and session."""

    __tablename__ = "conversation_turns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chatbot_id = Column(
        Integer, ForeignKey("chatbots.id"), nullable=False, index=True
    )
    session_id = Column(Integer, nullable=True, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(16), nullable=False)
    content = Column(UserEncryptedText, nullable=False)
    embedding_enc = Column(LargeBinary, nullable=True)
    turn_index = Column(Integer, nullable=False, default=0)
    call_chain_id = Column(String(36), nullable=True, index=True)
    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
    )


__all__ = ["ConversationTurn"]
