"""Worker initialization: state, provider flags, conversation handlers.

``LLMGenerateWorkerInitializationMixin`` owns the constructor, the
provider configuration flags, the small manager helpers, and the
conversation / history handlers that forward straight to the model
manager.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional

from airunner_services.contract_enums import ModelService, ModelStatus
from airunner_services.contract_enums import ModelType
from airunner_services.edge.model_management.llm_model_manager import (
    LLMModelManager,
)
from airunner_services.edge.workers.llm_generate_worker._state import (
    SignalCode,
)


class LLMGenerateWorkerInitializationMixin:
    """Constructor and shared helper surface for the LLM worker."""

    def __init__(self) -> None:
        """Initialize worker state and deferred LLM lifecycle helpers."""
        self.signal_handlers = {
            SignalCode.LLM_TEXT_GENERATE_REQUEST_SIGNAL: (
                self.on_llm_request_signal
            ),
            SignalCode.LLM_CLEAR_HISTORY_SIGNAL: (
                self.on_llm_clear_history_signal
            ),
            SignalCode.LLM_UNLOAD_SIGNAL: (self.on_llm_on_unload_signal),
            SignalCode.LLM_LOAD_SIGNAL: (self.on_llm_load_model_signal),
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
            SignalCode.RAG_INDEX_CANCEL: (self.on_rag_index_cancel_signal),
            SignalCode.RAG_LOAD_EMBEDDING: (
                self.on_rag_load_embedding_signal
            ),
        }
        self._model_manager: Optional[LLMModelManager] = None
        self._model_manager_lock = threading.Lock()
        self._interrupted = False
        self._download_dialog_showing = False
        self._download_dialog = None
        self._pending_llm_request = None
        self._pending_unload_request: Optional[Dict] = None
        self.manager_thread: Optional[object] = None
        self.download_manager = None
        super().__init__()
        self._llm_thread = None

        self._last_request_time: Optional[float] = None
        self._inactivity_timer: Optional[object] = None
        self._inactivity_timeout = 300
        self._auto_unload_enabled = False

    # ------------------------------------------------------------------
    # Provider configuration
    # ------------------------------------------------------------------

    @property
    def use_openrouter(self) -> bool:
        """Return whether the worker is configured for OpenRouter."""
        return (
            self.llm_generator_settings.model_service
            == ModelService.OPENROUTER.value
        )

    @property
    def use_ollama(self) -> bool:
        """Return whether the worker is configured for Ollama."""
        return (
            self.llm_generator_settings.model_service
            == ModelService.OLLAMA.value
        )

    @property
    def use_openai(self) -> bool:
        """Return whether the worker is configured for OpenAI."""
        return (
            self.llm_generator_settings.model_service
            == ModelService.OPENAI.value
        )

    @property
    def has_model_manager(self) -> bool:
        """Return whether the unified model manager is initialized."""
        return self._model_manager is not None

    def current_model_status(self) -> Optional[ModelStatus]:
        """Return the current local LLM status without creating a manager."""
        if self._model_manager is None:
            return None
        return self._model_manager.model_status.get(ModelType.LLM)

    @property
    def local_model_manager(self) -> LLMModelManager:
        """Return a model manager forced into local execution mode."""
        manager = LLMModelManager()
        manager.llm_settings.use_local_llm = True
        manager.llm_settings.use_openrouter = False
        manager.llm_settings.use_ollama = False
        return manager

    # ------------------------------------------------------------------
    # Conversation / history
    # ------------------------------------------------------------------

    def on_conversation_deleted_signal(self, data: Dict) -> None:
        """Forward conversation deletion to the model manager."""
        self.model_manager.on_conversation_deleted(data)

    def on_section_changed_signal(self, data: Dict = None) -> None:
        """Forward section changes to the model manager."""
        self.model_manager.on_section_changed()

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
                f"Error in on_load_conversation: {error}"
            )
