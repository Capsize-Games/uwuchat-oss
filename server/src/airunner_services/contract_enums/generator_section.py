"""Supported art generator sections."""

from enum import Enum


class GeneratorSection(Enum):
    """Supported art generator sections."""

    TXT2IMG = "txt2img"
    IMG2IMG = "img2img"
    INPAINT = "inpaint"
    OUTPAINT = "outpaint"
    UPSCALER = "x4-upscaler"
