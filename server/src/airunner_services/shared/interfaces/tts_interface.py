"""Common interface for text-to-speech — edge and cloud both satisfy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


class TTSInferenceInterface(ABC):
    """Abstract inference boundary for text-to-speech.

    Every TTS backend (local eSpeak, local OpenVoice/MeloTTS, ElevenLabs
    API, etc.) must satisfy this interface.
    """

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        **kwargs: Any,
    ) -> bytes:
        """Convert text to raw audio samples.

        Args:
            text: The text to speak.
            voice: Optional voice identifier (backend-specific).
            speed: Playback speed multiplier (1.0 = normal).
            **kwargs: Backend-specific tuning parameters.

        Returns:
            Raw audio bytes (format is backend-specific; typically WAV
            or raw PCM).
        """

    @abstractmethod
    def cancel(self) -> None:
        """Cancel the current synthesis on a best-effort basis."""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Return whether the TTS engine is ready."""

    @abstractmethod
    def load_model(self) -> None:
        """Prepare the TTS engine for synthesis."""

    @abstractmethod
    def unload_model(self) -> None:
        """Release TTS engine resources."""


__all__ = ["TTSInferenceInterface"]
