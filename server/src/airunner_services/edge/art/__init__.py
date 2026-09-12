"""Edge Art package — local image generation pipelines."""

from __future__ import annotations

from airunner_services.edge.art.art_generation_adapter import (
    ArtGenerationAdapter,
)
from airunner_services.edge.art.providers import (
    CONTROLNET_MODELS,
    DEFAULT_ART_VERSION,
    DEFAULT_IMAGE_GENERATOR,
    DEFAULT_SCHEDULER,
    GENERATOR_CAPABILITIES,
    MODEL_FILE_REQUIREMENTS,
    GeneratorCapabilities,
    get_capabilities,
    get_controlnet_models,
    get_file_requirements,
    get_schedulers_for_generator,
)

__all__ = [
    "ArtGenerationAdapter",
    "CONTROLNET_MODELS",
    "DEFAULT_ART_VERSION",
    "DEFAULT_IMAGE_GENERATOR",
    "DEFAULT_SCHEDULER",
    "GENERATOR_CAPABILITIES",
    "GeneratorCapabilities",
    "MODEL_FILE_REQUIREMENTS",
    "get_capabilities",
    "get_controlnet_models",
    "get_file_requirements",
    "get_schedulers_for_generator",
]
