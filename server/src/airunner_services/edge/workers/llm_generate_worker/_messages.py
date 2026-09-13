"""Message dispatch and generation result handling.

``LLMGenerateWorkerMessageMixin`` owns the queued-message dispatch, the
per-request generation run, and success / retry / error finalization.
"""

from __future__ import annotations

import asyncio
from typing import Dict

from airunner_services.contract_enums import LLMActionType
from airunner_services.edge.workers.llm_generate_worker._state import (
    SignalCode,
)
from airunner_services.llm.llm_response import LLMResponse
from airunner_services.utils.error_sanitizer import (
    sanitize_exception_message,
)


class LLMGenerateWorkerMessageMixin:
    """Queued-message dispatch and generation finalization."""

    def handle_message(self, message: Dict) -> None:
        """Process queued messages for LLM generation.

        Runs on the worker's own thread, which does not inherit the
        request context vars. Re-apply the tenant and DEK captured at
        dispatch time so conversation persistence targets the caller's
        schema and encrypted columns can be written. ``tenant_scope``
        and ``dek_scope`` always restore the previous value, preventing
        leakage between tenants on this long-lived thread.
        """
        from airunner_services.data.tenant import tenant_scope
        from airunner_services.utils.crypto.dek_cache import dek_scope

        is_dict = isinstance(message, dict)
        with tenant_scope(
            message.get("tenant_key") if is_dict else None
        ):
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
            self.logger.info("Processing download complete message from queue")
            self.on_huggingface_download_complete_signal(
                message.get("data", {})
            )
            return

        if self._interrupted:
            self.logger.info("Skipping message - worker interrupted")
            return

        self.logger.info(
            f"handle_message called with keys: {list(message.keys())}"
        )
        self.logger.info(f"request_id in message: {message.get('request_id')}")

        self._pending_llm_request = message
        self.logger.info(
            f"Stored pending request with ID: {message.get('request_id')}"
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
                f"Auto-loading {len(llm_request.rag_files)} RAG documents from request"
            )
            self._load_documents_into_rag(llm_request.rag_files)

        try:
            result = asyncio.run(manager.handle_request(message, {}))
        except Exception as error:
            self._handle_generation_error(message, error)
            return

        if result:
            self._finalize_generation(message, result)

    def _handle_generation_error(
        self, message: Dict, error: Exception
    ) -> None:
        """Emit an error response and clear state after a request failure."""
        self._pending_llm_request = None
        self.logger.exception(f"LLM request failed: {error}")
        self._emit_error_response(
            message, sanitize_exception_message(error)
        )
        self._queue_pending_unload_request()

    def _finalize_generation(self, message: Dict, result: Dict) -> None:
        """Apply success, retry, or error handling to a request result."""
        response_text = result.get("response", "")
        retry_after_download = bool(result.get("retry_after_download"))
        has_error = result.get("error") or (
            isinstance(response_text, str)
            and response_text.startswith("Error:")
        )

        if not has_error:
            self.logger.info(
                "Request completed successfully, clearing pending request"
            )
            self._pending_llm_request = None
        elif retry_after_download:
            self.logger.info(
                "Request failed while model download is still pending; "
                "keeping pending request for automatic retry"
            )
        else:
            self._pending_llm_request = None
            self.logger.info(
                "Request failed with non-retryable error, clearing pending request"
            )

            response_message = response_text or "Error invoking LLM"
            if not isinstance(response_message, str):
                response_message = str(response_message)
            self._emit_error_response(message, response_message)

        self._queue_pending_unload_request()

    def _emit_error_response(self, message: Dict, msg: str) -> None:
        """Emit one system error message via the streamed signal."""
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
