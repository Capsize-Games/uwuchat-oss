"""Pydantic models for art API routes, one model per file."""

from airunner_services.api.routes.art_contracts.art_component_response import (
    ArtComponentResponse,
)
from airunner_services.api.routes.art_contracts.background_removal_request import (
    BackgroundRemovalRequest,
)
from airunner_services.api.routes.art_contracts.generation_request import (
    GenerationRequest,
)
from airunner_services.api.routes.art_contracts.generation_response import (
    GenerationResponse,
)
from airunner_services.api.routes.art_contracts.job_status_response import (
    JobStatusResponse,
)
from airunner_services.api.routes.art_contracts.local_art_model import (
    LocalArtModel,
)
from airunner_services.api.routes.art_contracts.local_art_models_response import (
    LocalArtModelsResponse,
)
from airunner_services.api.routes.art_contracts.model_info import ModelInfo

__all__ = [
    "ArtComponentResponse",
    "BackgroundRemovalRequest",
    "GenerationRequest",
    "GenerationResponse",
    "JobStatusResponse",
    "LocalArtModel",
    "LocalArtModelsResponse",
    "ModelInfo",
]
