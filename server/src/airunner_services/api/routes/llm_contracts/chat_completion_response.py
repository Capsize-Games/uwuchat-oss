"""Chat completion response."""

from pydantic import BaseModel


class ChatCompletionResponse(BaseModel):
    """Chat completion response."""

    content: str
    model: str
    finish_reason: str
