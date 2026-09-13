"""Supported text-to-speech backends."""

from enum import Enum


class TTSModel(Enum):
    """Supported text-to-speech backends."""

    ESPEAK = "Espeak"
    OPENVOICE = "OpenVoice"
