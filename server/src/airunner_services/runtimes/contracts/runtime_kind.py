"""Runtime modality enum."""

from enum import Enum


class RuntimeKind(str, Enum):
    """Supported runtime modalities."""

    LLM = "llm"
    STT = "stt"
    TTS = "tts"
    ART = "art"
