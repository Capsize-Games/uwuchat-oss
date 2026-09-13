"""Edge STT package — local speech-to-text via faster-whisper."""

from __future__ import annotations

from airunner_services.edge.stt.faster_whisper_adapter import (
    FasterWhisperAdapter,
)
from airunner_services.edge.stt.providers import (
    DEFAULT_WHISPER_MODEL_FILENAME,
    DEFAULT_WHISPER_REPO,
    WHISPER_FILES,
    get_whisper_files,
    resolve_compute_type,
    resolve_device,
)

__all__ = [
    "DEFAULT_WHISPER_MODEL_FILENAME",
    "DEFAULT_WHISPER_REPO",
    "FasterWhisperAdapter",
    "WHISPER_FILES",
    "get_whisper_files",
    "resolve_compute_type",
    "resolve_device",
]
