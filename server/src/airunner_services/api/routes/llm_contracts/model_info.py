"""LLM model information."""

from typing import Optional

from pydantic import BaseModel


class ModelInfo(BaseModel):
    """LLM model information."""

    id: str
    name: str
    loaded: bool
    size_mb: Optional[int] = None
