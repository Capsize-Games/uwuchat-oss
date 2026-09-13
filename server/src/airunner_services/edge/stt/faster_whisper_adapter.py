"""Adapter wrapping FasterWhisperSTTExecutor behind the shared interface."""

from __future__ import annotations

from typing import Any

from airunner_services.shared.interfaces.stt_interface import (
    STTInferenceInterface,
)


class FasterWhisperAdapter(STTInferenceInterface):
    """Thin delegation adapter for the existing FasterWhisperSTTExecutor.

    The existing ``FasterWhisperSTTExecutor`` already implements
    :class:`STTInferenceInterface` (née STTExecutor), so this adapter
    simply delegates. It exists to establish the canonical import
    target under ``edge/`` and to allow future API-based STT adapters
    to live alongside it.
    """

    def __init__(self) -> None:
        self._executor: Any = None

    # ------------------------------------------------------------------
    # STTInferenceInterface
    # ------------------------------------------------------------------

    @property
    def stt_is_loaded(self) -> bool:
        if self._executor is None:
            return False
        return self._executor.stt_is_loaded

    def load(self, retry: bool = False) -> bool:
        return self._resolve_executor().load(retry=retry)

    def unload(self) -> None:
        if self._executor is not None:
            self._executor.unload()

    def transcribe(self, audio_data: Any) -> str:
        return self._resolve_executor().transcribe(audio_data)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _resolve_executor(self) -> Any:
        if self._executor is None:
            from airunner_services.edge.stt.faster_whisper_stt_executor import (
                FasterWhisperSTTExecutor,
            )

            self._executor = FasterWhisperSTTExecutor()
        return self._executor
