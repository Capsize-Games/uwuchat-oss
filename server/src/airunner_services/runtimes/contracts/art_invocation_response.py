"""Art invocation response contract."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ArtInvocationResponse(BaseModel):
    """Response payload for art generation execution."""

    model_config = ConfigDict(extra="forbid")

    images: List[str] = Field(default_factory=list)
    image_count: int = 0
    node_id: Optional[str] = None
