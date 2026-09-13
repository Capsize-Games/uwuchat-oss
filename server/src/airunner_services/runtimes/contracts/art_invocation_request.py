"""Art invocation request contract."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ArtInvocationRequest(BaseModel):
    """Request payload for art generation execution."""

    model_config = ConfigDict(extra="forbid")

    prompt: str
    negative_prompt: str = ""
    model: Optional[str] = None
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg_scale: float = 7.5
    seed: Optional[int] = None
    num_images: int = 1
    stream: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
