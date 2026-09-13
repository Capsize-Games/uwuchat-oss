"""Generation job status."""

from typing import Optional

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    """Generation job status."""

    job_id: str
    status: str
    progress: float
    image_url: Optional[str] = None
    image: Optional[str] = None
    error: Optional[str] = None
