"""Queued-message dispatch and in-flight conversation tracking.

``BaseLLMWorkerMessageMixin`` owns ``handle_message`` (which re-applies
the tenant / DEK scope on the worker thread) and the dispatch of each
payload type, including the generation attempt and its cleanup.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from airunner_services.workers.base_llm_worker._state import (
    _IN_FLIGHT_CONVERSATION_IDS,
    _IN_FLIGHT_LOCK,
)


class BaseLLMWorkerMessageMixin:
    """Dispatch queued payloads and track in-flight generations."""

    def handle_message(self, message: Dict) -> None:
        """Process queued messages for LLM generation.

        Runs on the worker's own thread, which does not inherit the
        request context vars.  Re-applies the tenant and DEK captured at
        dispatch time so conversation persistence targets the caller's
        schema and encrypted columns can be written.
        """
        from airunner_services.data.tenant import tenant_scope
        from airunner_services.utils.crypto.dek_cache import dek_scope

        is_dict = isinstance(message, dict)
        with tenant_scope(message.get("tenant_key") if is_dict else None):
            with dek_scope(message.get("dek") if is_dict else None):
                self._handle_message(message)

    def _handle_message(self, message: Dict) -> None:
        """Dispatch one queued worker payload (tenant context applied)."""
        message_type = message.get("_message_type")
        if message_type == "llm_load":
            self.on_llm_load_model_signal(message.get("data", {}))
            return
        if message_type == "llm_unload":
            self.on_llm_on_unload_signal(message.get("data", {}))
            return

        if message.get("_message_type") == "download_complete":
            self.logger.info(
                "Processing download complete message from queue",
            )
            self.on_huggingface_download_complete_signal(
                message.get("data", {}),
            )
            return

        if self._interrupted:
            self.logger.info("Skipping message - worker interrupted")
            self._clear_in_flight_conversation(message)
            return

        self.logger.info(
            "handle_message called with keys: %s",
            list(message.keys()),
        )
        self.logger.info(
            "request_id in message: %s",
            message.get("request_id"),
        )

        self._pending_llm_request = message
        self.logger.info(
            "Stored pending request with ID: %s",
            message.get("request_id"),
        )

        self._handle_generation(message)

    def _handle_generation(self, message: Dict) -> None:
        """Run one generation request through the model manager."""
        manager = self.model_manager
        request_data = message.get("request_data", {})
        llm_request = request_data.get("llm_request")

        if (
            llm_request.rag_files is not None
            and len(llm_request.rag_files) > 0
        ):
            self.logger.info(
                "Auto-loading %d RAG documents from request",
                len(llm_request.rag_files),
            )
            self._load_documents_into_rag(llm_request.rag_files)

        try:
            result = asyncio.run(manager.handle_request(message, {}))
        except Exception as error:
            self._handle_generation_error(message, error)
            return

        if not result:
            self._clear_in_flight_conversation(message)
            return

        self._finalize_generation(message, result)

    def _handle_generation_error(
        self,
        message: Dict,
        error: Exception,
    ) -> None:
        """Log, emit, and clean up after a failed generation."""
        self._pending_llm_request = None
        from airunner_services.utils.network_retry import (
            is_transient_network_error,
            log_network_failure,
        )
        if is_transient_network_error(error):
            log_network_failure(
                self.logger, "LLM request failed", error
            )
        else:
            self.logger.exception(
                "LLM request failed: %s", error
            )
        self._emit_error_response(message, error)
        self._queue_pending_unload_request()
        self._clear_in_flight_conversation(message)

    def _finalize_generation(
        self,
        message: Dict,
        result: Dict,
    ) -> None:
        """Clear pending state after one generation completes/fails."""
        response_text = result.get("response", "")
        retry_after_download = bool(result.get("retry_after_download"))
        has_error = result.get("error") or (
            isinstance(response_text, str)
            and response_text.startswith("Error:")
        )

        if not has_error:
            self.logger.info(
                "Request completed successfully, clearing pending request",
            )
            self._pending_llm_request = None
        elif retry_after_download:
            self.logger.info(
                "Request failed while model download is still pending; "
                "keeping pending request for automatic retry",
            )
        else:
            self._pending_llm_request = None
            self.logger.info(
                "Request failed with non-retryable error, "
                "clearing pending request",
            )
            self._emit_error_response(
                message,
                response_text or "Error invoking LLM",
            )

        self._clear_in_flight_conversation(message)
        self._queue_pending_unload_request()

    @staticmethod
    def _clear_in_flight_conversation(message: dict) -> None:
        """Remove the conversation tracked by *message* from the
        in-flight set (if present).  Safe to call when no
        conversation was tracked.
        """
        conversation_id = message.get("conversation_id")
        if isinstance(conversation_id, int) and conversation_id > 0:
            with _IN_FLIGHT_LOCK:
                _IN_FLIGHT_CONVERSATION_IDS.discard(conversation_id)
