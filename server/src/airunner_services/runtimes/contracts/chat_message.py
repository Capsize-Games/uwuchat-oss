"""Neutral chat message contract."""

from typing import Optional

from pydantic import BaseModel, ConfigDict

from airunner_services.runtimes.contracts.message_role import MessageRole


class ChatMessage(BaseModel):
    """Neutral chat message representation."""

    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str
    name: Optional[str] = None
