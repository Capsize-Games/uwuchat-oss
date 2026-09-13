"""Worker response payload codes."""

from enum import Enum


class EngineResponseCode(Enum):
    """Worker response payload codes."""

    NONE = 0
    STATUS = 100
    ERROR = 200
    WARNING = 300
    PROGRESS = 400
    IMAGE_GENERATED = 500
    CONTROLNET_IMAGE_GENERATED = 501
    MASK_IMAGE_GENERATED = 502
    EMBEDDING_LOAD_FAILED = 600
    TEXT_GENERATED = 700
    TEXT_STREAMED = 701
    CAPTION_GENERATED = 800
    ADD_TO_CONVERSATION = 900
    CLEAR_MEMORY = 1000
    INSUFFICIENT_GPU_MEMORY = 1200
    INTERRUPTED = 1300
