"""STT invocation response contract."""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class STTInvocationResponse(BaseModel):
    """Response payload for speech-to-text execution."""

    model_config = ConfigDict(extra="forbid")

    text: str
    language: Optional[str] = None
