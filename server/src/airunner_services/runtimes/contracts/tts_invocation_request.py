"""TTS invocation request contract."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class TTSInvocationRequest(BaseModel):
    """Request payload for text-to-speech execution."""

    model_config = ConfigDict(extra="forbid")

    text: str
    model: Optional[str] = None
    voice: Optional[str] = None
    speed: float = 1.0
    stream: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
