"""One local art model file."""

from pydantic import BaseModel


class LocalArtModel(BaseModel):
    """One local art model file."""

    id: str
    name: str
    path: str
    size_bytes: int
