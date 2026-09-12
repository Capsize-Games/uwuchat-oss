"""OpenVoice/MeloTTS adapter implementing the shared TTSInferenceInterface."""

from __future__ import annotations

from typing import Any, Optional

from airunner_services.shared.interfaces.tts_interface import (
    TTSInferenceInterface,
)


class OpenVoiceAdapter(TTSInferenceInterface):
    """TTS adapter backed by the local OpenVoice/MeloTTS engine."""

    def __init__(self) -> None:
        self._manager: Any = None

    # ------------------------------------------------------------------
    # TTSInferenceInterface
    # ------------------------------------------------------------------

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0,
        **kwargs: Any,
    ) -> bytes:
        manager = self._manager or self._build_manager()
        return manager.synthesize(text, voice=voice, speed=speed, **kwargs)

    def cancel(self) -> None:
        pass  # OpenVoice currently has no interrupt mechanism.

    @property
    def is_loaded(self) -> bool:
        return self._manager is not None

    def load_model(self) -> None:
        self._build_manager()

    def unload_model(self) -> None:
        self._manager = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_manager(self) -> Any:
        from airunner_services.edge.tts.openvoice_model_manager import (
            OpenVoiceModelManager,
        )

        self._manager = OpenVoiceModelManager()
        return self._manager
