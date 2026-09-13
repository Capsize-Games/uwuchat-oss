"""Background-removal request payload."""

from pydantic import BaseModel


class BackgroundRemovalRequest(BaseModel):
    """Background-removal request payload."""

    image_b64: str
