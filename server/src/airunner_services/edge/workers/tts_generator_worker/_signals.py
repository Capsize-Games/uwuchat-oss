"""Signal entry points and runtime control for the TTS worker."""

from __future__ import annotations

import queue
from typing import Dict, Optional

from airunner_services.contract_enums import (
    LLMActionType,
    ModelStatus,
    TTSModel,
)
from airunner_services.llm.thinking_parser import (
    normalize_thinking_content,
    strip_thinking_tags,
)


class TTSGeneratorWorkerSignalsMixin:
    """Handle TTS-relevant application signals and streamed text."""

    def on_llm_thinking_signal(self, data: Optional[Dict]) -> None:
        """Track active reasoning so TTS only speaks final visible text."""
        if not isinstance(data, dict):
            return

        self._sync_llm_stream_state(
            data.get("request_id"),
        )

        status = str(data.get("status", "")).strip().lower()
        if status == "started":
            self._llm_thinking_active = True
            self._llm_thinking_content = None
            return
        if status == "streaming":
            self._llm_thinking_active = True
            return
        if status == "completed":
            self._llm_thinking_active = False
            self._llm_thinking_content = normalize_thinking_content(
                data.get("content")
            )

    def on_llm_text_streamed_signal(self, data):
        response = data.get("response", None)
        if data.get("_skip_worker_manager_tts"):
            return
        if response is not None and getattr(
            response, "skip_tts_stream", False
        ):
            return
        if not self.tts_enabled:
            return

        if not response:
            raise ValueError("No LLMResponse object found in data")

        if response.action is LLMActionType.GENERATE_IMAGE:
            return

        if getattr(response, "is_system_message", False):
            return

        self._sync_llm_stream_state(
            getattr(response, "request_id", None),
            is_first_message=bool(
                getattr(response, "is_first_message", False)
            ),
        )

        cleaned_message = strip_thinking_tags(response.message).replace(
            "</s>",
            "",
        )
        if cleaned_message:
            self._llm_raw_visible_chunks.append(cleaned_message)

        if self._has_daemon_tts_capability():
            if self.do_interrupt:
                self.logger.debug("Unblocking TTS due to new message")
                self.on_unblock_tts_generator_signal(None)
            if response.is_end_of_message:
                final_message = self._current_visible_tts_text().strip()
                if final_message:
                    if final_message[-1] not in ".!?":
                        final_message += "."
                    self._generate_daemon_visible_reply_async(final_message)
                self._reset_llm_stream_state()
            return

        if not response.is_end_of_message:
            return

        queued_message = (
            getattr(response, "final_visible_message", None)
            or self._current_visible_tts_text().strip()
        )
        if not queued_message:
            self._reset_llm_stream_state()
            return

        active_model = self._active_tts_model()
        failed_local_model = (
            active_model is not None
            and getattr(self, "_failed_model", None) == active_model
        )
        if not self._has_daemon_tts_capability() and not failed_local_model:
            if not self.tts or self._current_tts_status() not in [
                ModelStatus.LOADED,
                ModelStatus.LOADING,
            ]:
                self._load_tts()

        if self.do_interrupt:
            self.logger.debug("Unblocking TTS due to new message")
            self.on_unblock_tts_generator_signal(None)

        if queued_message[-1] not in ".!?":
            queued_message += "."

        self.add_to_queue(
            {
                "message": queued_message,
                "is_end_of_message": True,
            }
        )

        self._reset_llm_stream_state()

    def on_interrupt_process_signal(self, data: dict = None):
        client = self._daemon_client()
        request_id = self._active_request_id
        if client is not None and request_id is not None:
            try:
                client.cancel_runtime(
                    "tts",
                    deployment_mode="local_fallback",
                    request_id=request_id,
                    auto_start=False,
                )
            except RuntimeError:
                pass
            self._active_request_id = None
        self.play_queue = []
        self.play_queue_started = False
        self.tokens = []
        self._sentence_buffer = []
        self.queue = queue.Queue()
        self.do_interrupt = True
        self.paused = True
        self._reset_llm_stream_state()
        if self.tts:
            self.tts.interrupt_process_signal()

    def on_unblock_tts_generator_signal(self, data: Optional[Dict]):
        if self.tts_enabled:
            self.logger.debug("Unblocking TTS generation...")
            self.do_interrupt = False
            self.paused = False
            if self.tts:
                self.tts.unblock_tts_generator_signal()
        if data is not None:
            callback = data.get("callback", None)
            if callback is not None:
                callback()

    def on_enable_tts_signal(self, data: dict = None):
        self.logger.debug("ON ENABLE TTS SIGNAL")
        self._failed_model = None
        self._load_tts()

    def on_disable_tts_signal(self, data: dict = None):
        self._unload_tts()

    def start_worker_thread(self):
        if self.tts_enabled:
            self._load_tts()
