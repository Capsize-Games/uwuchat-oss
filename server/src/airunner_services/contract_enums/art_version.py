"""Supported art model versions available for inference."""

from enum import Enum


class ArtVersion(Enum):
    """Supported art model versions available for inference."""

    NONE = "None"
    SDXL1_0 = "SDXL 1.0"
    SDXL_LIGHTNING = "SDXL Lightning"
    SDXL_HYPER = "SDXL Hyper"
    X4_UPSCALER = "x4-upscaler"
    Z_IMAGE_TURBO = "Z-Image Turbo"
