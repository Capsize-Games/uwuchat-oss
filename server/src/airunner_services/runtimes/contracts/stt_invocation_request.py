"""STT invocation request contract."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class STTInvocationRequest(BaseModel):
    """Request payload for speech-to-text execution."""

    model_config = ConfigDict(extra="forbid")

    model: Optional[str] = None
    audio_b64: str
    mime_type: str = "audio/wav"
    language: Optional[str] = None
    sample_rate: Optional[int] = None
    stream: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
