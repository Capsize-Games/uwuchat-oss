"""Text completion response."""

from pydantic import BaseModel


class CompletionResponse(BaseModel):
    """Text completion response."""

    text: str
    finish_reason: str
