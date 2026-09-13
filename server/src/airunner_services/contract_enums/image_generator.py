"""Supported image generators."""

from enum import Enum


class ImageGenerator(Enum):
    """Supported image generators."""

    STABLEDIFFUSION = "stablediffusion"
    ZIMAGE = "zimage"
