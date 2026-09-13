"""Per-response LLM stream state and visible-text tracking for TTS."""

from __future__ import annotations

import threading
from typing import Optional

from airunner_services.llm.thinking_parser import (
    strip_stored_thinking_prefix,
)


class TTSGeneratorWorkerStreamStateMixin:
    """Track one LLM response's visible text for streaming TTS."""

    def _reset_llm_stream_state(self) -> None:
        """Clear per-response visible/thinking tracking for TTS."""
        self._llm_request_id = None
        self._llm_raw_visible_chunks = []
        self._llm_spoken_visible_text = ""
        self._llm_thinking_active = False
        self._llm_thinking_content = None

    def _sync_llm_stream_state(
        self,
        request_id: Optional[str],
        *,
        is_first_message: bool = False,
    ) -> None:
        """Reset TTS stream state when one new LLM response begins."""
        if not hasattr(self, "_llm_raw_visible_chunks"):
            self._reset_llm_stream_state()

        current_request_id = getattr(self, "_llm_request_id", None)
        same_request = bool(request_id) and request_id == current_request_id
        if (
            request_id
            and current_request_id
            and request_id != current_request_id
        ) or (is_first_message and not same_request):
            self._reset_llm_stream_state()
            current_request_id = None
        if request_id and current_request_id is None:
            self._llm_request_id = request_id

    def _visible_tts_delta(self) -> str:
        """Return one newly visible reply fragment safe to speak."""
        if getattr(self, "_llm_thinking_active", False):
            return ""

        raw_chunks = getattr(self, "_llm_raw_visible_chunks", [])
        visible_text = strip_stored_thinking_prefix(
            "".join(raw_chunks),
            getattr(self, "_llm_thinking_content", None),
        )
        spoken_text = getattr(self, "_llm_spoken_visible_text", "")

        if not visible_text or visible_text == spoken_text:
            return ""
        if not spoken_text:
            self._llm_spoken_visible_text = visible_text
            return visible_text
        if visible_text.startswith(spoken_text):
            delta = visible_text[len(spoken_text) :]
            self._llm_spoken_visible_text = visible_text
            return delta

        self._llm_spoken_visible_text = visible_text
        return visible_text

    def _current_visible_tts_text(self) -> str:
        """Return the full visible reply currently buffered for speech."""
        if getattr(self, "_llm_thinking_active", False):
            return ""
        return strip_stored_thinking_prefix(
            "".join(getattr(self, "_llm_raw_visible_chunks", [])),
            getattr(self, "_llm_thinking_content", None),
        )

    def _generate_daemon_visible_reply_async(self, message: str) -> None:
        """Generate one daemon-backed GUI reply without the worker queue hop."""
        threading.Thread(
            target=self._generate,
            args=(message,),
            daemon=True,
        ).start()

    def _forward_gui_audio_response(self, response) -> bool:
        """Forward one synthesized audio buffer into the live GUI playback path."""
        api = self._current_api()
        if api is None or False:
            return False
        main_window = getattr(api, "main_window", None) or getattr(
            getattr(api, "app", None),
            "main_window",
            None,
        )
        if main_window is None:
            return False
        worker_manager = getattr(main_window, "worker_manager", None)
        if worker_manager is None:
            return False
        handler = getattr(
            worker_manager,
            "on_tts_generator_worker_add_to_stream_signal",
            None,
        )
        if not callable(handler):
            return False
        handler({"message": response})
        return True
