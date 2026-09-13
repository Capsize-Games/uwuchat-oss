"""Shared inference interfaces used by both edge and cloud implementations."""

from __future__ import annotations

from airunner_services.shared.interfaces.llm_interface import (
    LLMInferenceInterface,
)
from airunner_services.shared.interfaces.art_interface import (
    ArtInferenceInterface,
)
from airunner_services.shared.interfaces.tts_interface import (
    TTSInferenceInterface,
)
from airunner_services.shared.interfaces.stt_interface import (
    STTInferenceInterface,
)

__all__ = [
    "ArtInferenceInterface",
    "LLMInferenceInterface",
    "STTInferenceInterface",
    "TTSInferenceInterface",
]
