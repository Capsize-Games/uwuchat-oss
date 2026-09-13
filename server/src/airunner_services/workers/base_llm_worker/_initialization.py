"""Worker initialization: state, abstract members, provider helpers.

``BaseLLMWorkerInitializationMixin`` owns the constructor, the
abstract members subclasses must provide, the small provider helper
properties, and the conversation / history handlers that forward
straight to the model manager.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Dict, Optional

from airunner_services.contract_enums import ModelStatus, ModelType
from airunner_services.workers.base_llm_worker._state import SignalCode

if TYPE_CHECKING:
    from airunner_services.model_management.llm_model_manager import (
        LLMModelManager,
    )


class BaseLLMWorkerInitializationMixin:
    """Constructor and shared helper surface for the base LLM worker."""

    def __init__(self) -> None:
        """Initialise worker state and signal-to-handler mapping."""
        self.signal_handlers: dict = {
            SignalCode.LLM_TEXT_GENERATE_REQUEST_SIGNAL: (
                self.on_llm_request_signal
            ),
            SignalCode.LLM_CLEAR_HISTORY_SIGNAL: (
                self.on_llm_clear_history_signal
            ),
            SignalCode.LLM_UNLOAD_SIGNAL: self.on_llm_on_unload_signal,
            SignalCode.LLM_LOAD_SIGNAL: self.on_llm_load_model_signal,
            SignalCode.RAG_INDEX_ALL_DOCUMENTS: (
                self.on_rag_index_all_documents_signal
            ),
            SignalCode.RAG_INDEX_SELECTED_DOCUMENTS: (
                self.on_rag_index_selected_documents_signal
            ),
            SignalCode.RAG_INDEXING_PROGRESS: (
                self.on_rag_indexing_progress_signal
            ),
            SignalCode.RAG_INDEXING_COMPLETE: (
                self.on_rag_indexing_complete_signal
            ),
            SignalCode.RAG_INDEX_CANCEL: self.on_rag_index_cancel_signal,
            SignalCode.RAG_LOAD_EMBEDDING: self.on_rag_load_embedding_signal,
        }
        self._model_manager: Optional[LLMModelManager] = None
        self._model_manager_lock = threading.Lock()
        self._interrupted = False
        self._download_dialog_showing = False
        self._download_dialog = None
        self._pending_llm_request: Optional[Dict] = None
        self._pending_unload_request: Optional[Dict] = None
        self.manager_thread: Optional[object] = None
        self.download_manager = None
        super().__init__()
        self._llm_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Abstract — subclasses must provide
    # ------------------------------------------------------------------

    @property
    def model_manager(self) -> LLMModelManager:
        """Return the shared model manager for the active provider."""
        raise NotImplementedError

    def on_llm_on_unload_signal(self, data: Optional[Dict] = None) -> None:
        """Handle a queued unload request."""
        raise NotImplementedError

    def on_llm_load_model_signal(self, data: Dict) -> None:
        """Handle a queued model-load request."""
        raise NotImplementedError

    def _update_activity_timestamp(self) -> None:
        """Refresh the last-request timestamp (no-op in base)."""

    # ------------------------------------------------------------------
    # Provider helpers
    # ------------------------------------------------------------------

    @property
    def has_model_manager(self) -> bool:
        """Return whether the unified model manager is initialised."""
        return self._model_manager is not None

    def current_model_status(self) -> Optional[ModelStatus]:
        """Return the current LLM status without creating a manager."""
        if self._model_manager is None:
            return None
        return self._model_manager.model_status.get(ModelType.LLM)

    # ------------------------------------------------------------------
    # Conversation / history
    # ------------------------------------------------------------------

    def on_conversation_deleted_signal(self, data: Dict) -> None:
        """Forward conversation deletion to the model manager."""
        self.model_manager.on_conversation_deleted(data)

    def on_llm_clear_history_signal(
        self, data: Optional[Dict] = None
    ) -> None:
        """Forward the clear-history request to the model manager."""
        if self._model_manager:
            self._model_manager.clear_history(data)

    def on_llm_add_chatbot_response_to_history(
        self,
        message: Dict,
    ) -> None:
        """Add one chatbot response to the conversation history."""
        self.model_manager.add_chatbot_response_to_history(message)

    def on_llm_load_conversation(self, message: Dict) -> None:
        """Load one conversation into the model manager."""
        try:
            self.model_manager.load_conversation(message)
        except Exception as error:
            self.logger.error(
                "Error in on_load_conversation: %s",
                error,
            )
