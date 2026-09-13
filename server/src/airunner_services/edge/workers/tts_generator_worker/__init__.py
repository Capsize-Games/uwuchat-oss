"""Service-owned TTS generator worker.

Decomposed into focused modules:

- ``_stream_state`` — per-response LLM stream state and visible-text tracking
- ``_api_resolution`` — application/API resolution and TTS capability probes
- ``_signals`` — signal entry points and runtime control
- ``_model_lifecycle`` — TTS model manager load/unload lifecycle
- ``_queue`` — worker-thread message queue handling
- ``_generation`` — TTS generation, daemon synthesis path, and audio decoding

``TTSGeneratorWorker`` is the composed public class; all existing importers
keep working unchanged.
"""

from __future__ import annotations

from typing import Optional

from airunner_services.edge.workers.tts_generator_worker._api_resolution import (
    TTSGeneratorWorkerApiResolutionMixin,
)
from airunner_services.edge.workers.tts_generator_worker._generation import (
    SignalCode,
    TTSGeneratorWorkerGenerationMixin,
)
from airunner_services.edge.workers.tts_generator_worker._model_lifecycle import (
    TTSGeneratorWorkerModelLifecycleMixin,
)
from airunner_services.edge.workers.tts_generator_worker._queue import (
    TTSGeneratorWorkerQueueMixin,
)
from airunner_services.edge.workers.tts_generator_worker._signals import (
    TTSGeneratorWorkerSignalsMixin,
)
from airunner_services.edge.workers.tts_generator_worker._stream_state import (
    TTSGeneratorWorkerStreamStateMixin,
)
from airunner_services.workers.worker import QueueType, Worker


class TTSGeneratorWorker(
    TTSGeneratorWorkerStreamStateMixin,
    TTSGeneratorWorkerApiResolutionMixin,
    TTSGeneratorWorkerSignalsMixin,
    TTSGeneratorWorkerModelLifecycleMixin,
    TTSGeneratorWorkerQueueMixin,
    TTSGeneratorWorkerGenerationMixin,
    Worker,
):
    """Generate TTS audio from streamed or queued text."""

    tokens = []
    queue_type = QueueType.GET_NEXT_ITEM

    SENTENCE_BUFFER_SIZE = 2
    MIN_WORDS_FOR_GENERATION = 8
    DAEMON_MIN_WORDS_FOR_GENERATION = 4

    def __init__(self, *args, **kwargs):
        self.tts = None
        self.play_queue = []
        self.play_queue_started = False
        self.do_interrupt = False
        self._current_model: Optional[str] = None
        self._failed_model: Optional[str] = None
        self._sentence_buffer = []
        self._active_request_id: Optional[str] = None
        self._reset_llm_stream_state()
        self.signal_handlers = {
            SignalCode.TTS_ENABLE_SIGNAL: self.on_enable_tts_signal,
        }
        super().__init__()


__all__ = [
    "QueueType",
    "SignalCode",
    "TTSGeneratorWorker",
    "Worker",
]
