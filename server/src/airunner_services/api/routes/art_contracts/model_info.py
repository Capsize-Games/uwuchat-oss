"""Art model information."""

from pydantic import BaseModel


class ModelInfo(BaseModel):
    """Art model information."""

    id: str
    name: str
    loaded: bool
    type: str
