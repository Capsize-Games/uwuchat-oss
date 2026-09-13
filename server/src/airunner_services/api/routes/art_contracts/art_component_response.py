"""Art component control response."""

from pydantic import BaseModel


class ArtComponentResponse(BaseModel):
    """Art component control response."""

    component: str
    status: str
