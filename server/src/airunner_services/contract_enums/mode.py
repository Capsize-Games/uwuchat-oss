"""Top-level application modes."""

from enum import Enum


class Mode(Enum):
    """Top-level application modes."""

    IMAGE = "Image Generation"
    LANGUAGE_PROCESSOR = "Language Processing"
    MODEL_MANAGER = "Model Manager"
