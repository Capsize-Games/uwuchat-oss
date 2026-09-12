"""Model load request."""

from pydantic import BaseModel


class ModelLoadRequest(BaseModel):
    """Model load request."""

    model_id: str
