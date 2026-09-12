"""Edge TTS package — local text-to-speech engines."""

from __future__ import annotations

from airunner_services.edge.tts.espeak_adapter import EspeakAdapter
from airunner_services.edge.tts.openvoice_adapter import OpenVoiceAdapter
from airunner_services.edge.tts.providers import (
    ESPEAK_CONFIG,
    OPENVOICE_ALL_MODELS,
    OPENVOICE_LANGUAGES,
    SUPPORTED_TTS_ENGINES,
    get_all_openvoice_files,
    get_espeak_config,
    get_openvoice_files_for_languages,
    language_name,
    supported_language_codes,
)

__all__ = [
    "ESPEAK_CONFIG",
    "EspeakAdapter",
    "OPENVOICE_ALL_MODELS",
    "OPENVOICE_LANGUAGES",
    "OpenVoiceAdapter",
    "SUPPORTED_TTS_ENGINES",
    "get_all_openvoice_files",
    "get_espeak_config",
    "get_openvoice_files_for_languages",
    "language_name",
    "supported_language_codes",
]
