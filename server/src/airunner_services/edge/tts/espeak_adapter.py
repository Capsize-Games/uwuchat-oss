"""eSpeak TTS adapter implementing the shared TTSInferenceInterface."""

from __future__ import annotations

from typing import Any, Optional

from airunner_services.shared.interfaces.tts_interface import (
    TTSInferenceInterface,
)


class EspeakAdapter(TTSInferenceInterface):
    """TTS adapter backed by the local eSpeak engine (pyttsx3)."""

    def __init__(self) -> None:
        self._engine: Any = None

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
        _ = self._engine or self._build_engine()
        # The eSpeak manager handles synthesis via pyttsx3 speak-to-file.
        from airunner_services.edge.tts.espeak_model_manager import (
            EspeakModelManager,
        )

        manager = EspeakModelManager()
        return manager.synthesize(text, voice=voice, speed=speed, **kwargs)

    def cancel(self) -> None:
        if self._engine is not None:
            try:
                self._engine.stop()
            except Exception:
                pass

    @property
    def is_loaded(self) -> bool:
        return self._engine is not None

    def load_model(self) -> None:
        self._build_engine()

    def unload_model(self) -> None:
        self._engine = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_engine(self) -> Any:
        import pyttsx3

        self._engine = pyttsx3.init()
        return self._engine
