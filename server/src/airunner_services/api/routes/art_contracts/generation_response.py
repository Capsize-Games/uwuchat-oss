"""Image generation response."""

from pydantic import BaseModel


class GenerationResponse(BaseModel):
    """Image generation response."""

    job_id: str
    status: str
