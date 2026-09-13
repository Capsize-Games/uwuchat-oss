"""Default values and normalizers for image generators."""

from airunner_services.contract_enums.art_version import ArtVersion
from airunner_services.contract_enums.image_generator import ImageGenerator

DEFAULT_IMAGE_GENERATOR = ImageGenerator.ZIMAGE
DEFAULT_ART_VERSION = ArtVersion.Z_IMAGE_TURBO


def normalize_image_generator_name(value: str | None) -> str:
    """Return a supported image generator name string."""
    if value in {item.value for item in ImageGenerator}:
        return str(value)
    return DEFAULT_IMAGE_GENERATOR.value


def normalize_art_version(value: str | None) -> str:
    """Return a supported art version string."""
    if value in {item.value for item in ArtVersion}:
        return str(value)
    return DEFAULT_ART_VERSION.value
