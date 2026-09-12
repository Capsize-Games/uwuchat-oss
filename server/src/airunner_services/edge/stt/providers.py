"""Edge STT provider configuration — Whisper model metadata and paths.

This module contains file requirements, model download metadata, and
device/compute-type resolution for local faster-whisper inference.
"""

from __future__ import annotations

from typing import Dict, List

# ------------------------------------------------------------------
# Supported Whisper models
# ------------------------------------------------------------------

# Default HuggingFace repo and model file for the whisper.cpp GGML model.
DEFAULT_WHISPER_REPO = "ggerganov/whisper.cpp"
DEFAULT_WHISPER_MODEL_FILENAME = "ggml-large-v3.bin"

# Model file requirements for download validation.
WHISPER_FILES: Dict[str, List[str]] = {
    DEFAULT_WHISPER_REPO: [DEFAULT_WHISPER_MODEL_FILENAME],
}

# ------------------------------------------------------------------
# Compute type configuration
# ------------------------------------------------------------------

# Map device strings to recommended faster-whisper compute types.
# See: https://github.com/SYSTRAN/faster-whisper
COMPUTE_TYPE_MAP: Dict[str, str] = {
    "cuda": "float16",
    "cpu": "int8",
    "auto": "auto",
}

DEFAULT_COMPUTE_TYPE = "auto"


def get_whisper_files() -> Dict[str, List[str]]:
    """Return a copy of the Whisper model file requirements."""
    return dict(WHISPER_FILES)


def resolve_compute_type(device: str) -> str:
    """Return the recommended compute type for one device.

    Args:
        device: ``"cuda"``, ``"cpu"``, or ``"auto"``.

    Returns:
        One of ``"float16"``, ``"int8"``, ``"int8_float16"``, or
        ``"auto"``.
    """
    compute = COMPUTE_TYPE_MAP.get(device, DEFAULT_COMPUTE_TYPE)
    if compute == "auto":
        import torch

        if torch.cuda.is_available():
            return "float16"
        return "int8"
    return compute


def resolve_device() -> str:
    """Return the preferred torch device for STT inference."""
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"
