"""Text completion request."""

from typing import Optional

from pydantic import BaseModel


class CompletionRequest(BaseModel):
    """Text completion request."""

    prompt: str
    gguf_runtime_profile: Optional[str] = None
    max_tokens: int = 100
    temperature: float = 0.7
