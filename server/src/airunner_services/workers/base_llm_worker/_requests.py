"""Request handling: generate, interrupt, and unload queueing.

``BaseLLMWorkerRequestMixin`` owns the generate-request signal (with
duplicate-generation prevention), the interrupt path, the deferred
unload request queueing, and the user-facing still-working / error
responses.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.llm_response import LLMResponse
from airunner_services.workers.base_llm_worker._state import (
    _IN_FLIGHT_CONVERSATION_IDS,
    _IN_FLIGHT_LOCK,
    SignalCode,
)


class BaseLLMWorkerRequestMixin:
    """Generate, interrupt, and deferred-unload request handling."""

    def on_llm_request_signal(self, message: dict) -> None:
        """Queue one incoming LLM request for generation.

        Rejects requests when a generation is already in flight for
        the same conversation, preventing duplicate (cost-doubling)
        work.
        """
        self.logger.info(
            "Received LLM request signal: %s",
            list(message.keys()),
        )
        if self._interrupted:
            self.logger.info(
                "Clearing interrupt flag - new message received",
            )
            self._interrupted = False

        conversation_id = message.get("conversation_id")
        if isinstance(conversation_id, int) and conversation_id > 0:
            with _IN_FLIGHT_LOCK:
                if conversation_id in _IN_FLIGHT_CONVERSATION_IDS:
                    self.logger.warning(
                        "Duplicate request for conversation %s — "
                        "generation already in flight, rejecting",
                        conversation_id,
                    )
                    self._emit_still_working(message)
                    return
                _IN_FLIGHT_CONVERSATION_IDS.add(conversation_id)

        request_id = message.get("request_id") or str(uuid.uuid4())
        message["request_id"] = request_id
        if isinstance(message.get("request_data"), dict):
            message["request_data"].setdefault("request_id", request_id)
        self.logger.debug(
            "Assigned request_id=%s to incoming request",
            request_id,
        )

        self._update_activity_timestamp()
        self.add_to_queue(message)
        self.logger.info("Added request to queue")

    def llm_on_interrupt_process_signal(self, data=None) -> None:
        """Interrupt the active generation and clear queued work."""
        self._interrupted = True
        self.clear_queue()
        self.logger.info(
            "Interrupted and cleared LLM generation queue",
        )
        if hasattr(self, "_model_manager") and self._model_manager is not None:
            self.logger.info(
                "Calling do_interrupt on model_manager %s",
                id(self._model_manager),
            )
            try:
                self._model_manager.do_interrupt()
            except Exception as error:
                self.logger.error(
                    "Error calling do_interrupt(): %s",
                    error,
                    exc_info=True,
                )
        else:
            self.logger.warning(
                "Model manager not available for interrupt",
            )

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
            },
        )

    def _emit_still_working(self, message: dict) -> None:
        """Send a system message informing the client that a
        generation is already in progress for this conversation.
        """
        try:
            request_id = message.get("request_id") or str(uuid.uuid4())
            response = LLMResponse(
                message=(
                    "Still working on your last message — "
                    "please wait for it to finish before "
                    "sending another."
                ),
                is_first_message=True,
                is_end_of_message=True,
                sequence_number=0,
                action=LLMActionType.CHAT,
                request_id=request_id,
                is_system_message=True,
            )
            self.emit_signal(
                SignalCode.LLM_TEXT_STREAMED_SIGNAL,
                {"response": response, "request_id": request_id},
            )
        except Exception:
            pass

    def _emit_error_response(
        self,
        message: Dict,
        error: Any,
    ) -> None:
        """Emit one error system-message through the streamed signal."""
        try:
            request_id = message.get("request_id")
            action = None
            try:
                action = message.get("request_data", {}).get("action")
            except Exception:
                action = None
            action_val = (
                action
                if isinstance(action, LLMActionType)
                else LLMActionType.CHAT
            )
            from airunner_services.utils.error_sanitizer import (
                sanitize_exception_message,
            )

            msg = (
                sanitize_exception_message(error)
                if isinstance(error, BaseException)
                else str(error)
            )
            response = LLMResponse(
                message=msg,
                is_first_message=True,
                is_end_of_message=True,
                sequence_number=0,
                action=action_val,
                request_id=request_id,
                is_system_message=True,
            )
            self.emit_signal(
                SignalCode.LLM_TEXT_STREAMED_SIGNAL,
                {"response": response, "request_id": request_id},
            )
        except Exception:
            pass
