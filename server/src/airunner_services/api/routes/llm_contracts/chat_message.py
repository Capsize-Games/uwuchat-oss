"""Chat message submitted to the HTTP API."""

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """Chat message submitted to the HTTP API."""

    role: str
    content: str
