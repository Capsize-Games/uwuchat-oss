"""ContextVar-based chatbot scoping for the knowledge system.

Set before each workflow run so knowledge tools know which agent's
facts to read and write without changing tool signatures.

subject='user'  — facts the character knows about the user (default)
subject='self'  — facts the character knows about itself
subject='world' — facts about named third parties, places, things,
                  organizations, concepts, or events, or general
                  objective knowledge (not about the user or character)
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_knowledge_chatbot_id: ContextVar[Optional[int]] = ContextVar(
    "knowledge_chatbot_id", default=None
)

_knowledge_subject: ContextVar[str] = ContextVar(
    "knowledge_subject", default="user"
)


def set_knowledge_chatbot_id(chatbot_id: Optional[int]) -> None:
    """Bind a chatbot_id to the current asyncio task for knowledge tools."""
    _knowledge_chatbot_id.set(chatbot_id)


def get_knowledge_chatbot_id() -> Optional[int]:
    """Return the chatbot_id bound to the current asyncio task."""
    return _knowledge_chatbot_id.get()


def set_knowledge_subject(subject: str) -> None:
    """Bind a subject ('user', 'self', or 'world') for the current
    knowledge operation."""
    _knowledge_subject.set(subject)


def get_knowledge_subject() -> str:
    """Return the knowledge subject bound to the current asyncio task."""
    return _knowledge_subject.get()
