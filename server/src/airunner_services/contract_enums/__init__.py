"""Service-owned enum definitions, one enum per file."""

from airunner_services.contract_enums.art_version import ArtVersion
from airunner_services.contract_enums.available_language import (
    AvailableLanguage,
)
from airunner_services.contract_enums.canvas_tool_name import CanvasToolName
from airunner_services.contract_enums.engine_response_code import (
    EngineResponseCode,
)
from airunner_services.contract_enums.gender import Gender
from airunner_services.contract_enums.generator_section import (
    GeneratorSection,
)
from airunner_services.contract_enums.image_generator import ImageGenerator
from airunner_services.contract_enums.llm_action_type import LLMActionType
from airunner_services.contract_enums.mode import Mode
from airunner_services.contract_enums.model_service import ModelService
from airunner_services.contract_enums.model_status import ModelStatus
from airunner_services.contract_enums.model_type import ModelType
from airunner_services.contract_enums.normalizers import (
    DEFAULT_ART_VERSION,
    DEFAULT_IMAGE_GENERATOR,
    normalize_art_version,
    normalize_image_generator_name,
)
from airunner_services.contract_enums.scheduler import Scheduler
from airunner_services.contract_enums.signal_code import SignalCode
from airunner_services.contract_enums.tts_model import TTSModel

# Keep legacy alias so any external code importing StableDiffusionVersion
# still works.
StableDiffusionVersion = ArtVersion

__all__ = [
    "AvailableLanguage",
    "CanvasToolName",
    "DEFAULT_ART_VERSION",
    "DEFAULT_IMAGE_GENERATOR",
    "EngineResponseCode",
    "Gender",
    "GeneratorSection",
    "ImageGenerator",
    "LLMActionType",
    "Mode",
    "ModelService",
    "ModelStatus",
    "ModelType",
    "Scheduler",
    "SignalCode",
    "ArtVersion",
    "StableDiffusionVersion",
    "TTSModel",
    "normalize_art_version",
    "normalize_image_generator_name",
]
