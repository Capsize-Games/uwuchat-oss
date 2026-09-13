"""Request handling: generate, interrupt, and unload queueing.

``LLMGenerateWorkerRequestMixin`` owns the generate-request signal, the
interrupt path, and the deferred unload request queueing.
"""

from __future__ import annotations

import uuid
from typing import Dict, Optional


class LLMGenerateWorkerRequestMixin:
    """Generate-request, interrupt, and deferred-unload handling."""

    def on_llm_request_signal(self, message: dict) -> None:
        """Queue one incoming LLM request for generation."""
        self.logger.info(
            f"Received LLM request signal: {list(message.keys())}"
        )
        if self._interrupted:
            self.logger.info("Clearing interrupt flag - new message received")
            self._interrupted = False

        request_id = message.get("request_id") or str(uuid.uuid4())
        message["request_id"] = request_id
        if isinstance(message.get("request_data"), dict):
            message["request_data"].setdefault("request_id", request_id)
        self.logger.debug(
            f"Assigned request_id={request_id} to incoming request"
        )

        self._update_activity_timestamp()
        self.add_to_queue(message)
        self.logger.info("Added request to queue")

    def llm_on_interrupt_process_signal(self, data=None) -> None:
        """Interrupt the active generation and clear queued work."""
        self._interrupted = True
        self.clear_queue()
        self.logger.info("Interrupted and cleared LLM generation queue")

        if hasattr(self, "_model_manager") and self._model_manager is not None:
            self.logger.info(
                f"Calling do_interrupt on model_manager {id(self._model_manager)}"
            )
            try:
                self._model_manager.do_interrupt()
            except Exception as error:
                self.logger.error(
                    f"Error calling do_interrupt(): {error}",
                    exc_info=True,
                )
        else:
            self.logger.warning("Model manager not available for interrupt")

    def request_unload_after_interrupt(
        self,
        data: Optional[Dict] = None,
    ) -> bool:
        """Interrupt the current request and queue one unload."""
        if self._model_manager is None:
            return False

        request_data = dict(data or {})
        self.llm_on_interrupt_process_signal(request_data)
        self._pending_unload_request = request_data
        if self._pending_llm_request is None:
            self._queue_pending_unload_request()
        return True

    def _queue_pending_unload_request(self) -> None:
        """Queue any unload requested during or after interruption."""
        if self._pending_unload_request is None:
            return

        request_data = self._pending_unload_request
        self._pending_unload_request = None
        self.add_to_queue(
            {
                "_message_type": "llm_unload",
                "data": request_data,
            }
        )
