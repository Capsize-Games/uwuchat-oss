"""TTS invocation response contract."""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class TTSInvocationResponse(BaseModel):
    """Response payload for text-to-speech execution."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool = True
    audio_b64: Optional[str] = None
