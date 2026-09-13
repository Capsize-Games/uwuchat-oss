"""Response payload for local art models."""

from typing import List

from pydantic import BaseModel

from airunner_services.api.routes.art_contracts.local_art_model import (
    LocalArtModel,
)


class LocalArtModelsResponse(BaseModel):
    """Response payload for local art models."""

    base_dir: str
    models: List[LocalArtModel]
