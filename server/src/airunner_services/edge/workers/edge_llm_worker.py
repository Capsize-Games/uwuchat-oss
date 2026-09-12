"""Edge (local GGUF) LLM generation worker."""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional

from airunner_services.contract_enums import ModelService, ModelStatus
from airunner_services.contract_enums import ModelType
from airunner_services.edge.model_management.llm_model_manager import (
    LLMModelManager,
)
from airunner_services.settings import AIRUNNER_LLM_ON
from airunner_services.utils.application.runtime_primitives import QTimer
from airunner_services.workers.base_llm_worker import BaseLLMWorker


class EdgeLLMWorker(BaseLLMWorker):
    """Orchestrate LLM requests against a local GGUF model."""

    def __init__(self) -> None:
        """Initialise edge-specific state after shared setup."""
        super().__init__()
        self._last_request_time: Optional[float] = None
        self._inactivity_timer: Optional[object] = None
        self._inactivity_timeout = 300
        self._auto_unload_enabled = False

    # ------------------------------------------------------------------
    # Provider selection
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

    # ------------------------------------------------------------------
    # Model manager
    # ------------------------------------------------------------------

    @property
    def model_manager(self) -> LLMModelManager:
        """Return the shared model manager for local GGUF execution."""
        with self._model_manager_lock:
            if self._model_manager is None:
                self._model_manager = LLMModelManager()

                # LLMModelManager.__init__ already applied the project
                # model router (DIALOGUE) when AIRUNNER_PROJECT is set.
                # If a DIALOGUE rule is active, honour it; otherwise
                # fall back to the DB-level model_service setting.
                router = getattr(
                    self._model_manager,
                    "_model_router",
                    None,
                )
                if router is not None and router.rule("DIALOGUE"):
                    pass
                else:
                    db_api_key = (
                        getattr(
                            self.llm_generator_settings,
                            "api_key",
                            None,
                        )
                        or None
                    )
                    db_api_base_url = (
                        getattr(
                            self.llm_generator_settings,
                            "api_base_url",
                            None,
                        )
                        or None
                    )
                    if self.use_openrouter:
                        self._model_manager.llm_settings.use_local_llm = False
                        self._model_manager.llm_settings.use_openrouter = True
                        if db_api_key:
                            self._model_manager.llm_settings.openrouter_api_key = (
                                db_api_key
                            )
                    elif self.use_ollama:
                        self._model_manager.llm_settings.use_local_llm = False
                        self._model_manager.llm_settings.use_ollama = True
                        if db_api_base_url:
                            self._model_manager.llm_settings.ollama_base_url = (
                                db_api_base_url
                            )
                    elif self.use_openai:
                        self._model_manager.llm_settings.use_local_llm = False
                        self._model_manager.llm_settings.use_openai = True
                        if db_api_key:
                            self._model_manager.llm_settings.openai_api_key = (
                                db_api_key
                            )
                    else:
                        self._model_manager.llm_settings.use_local_llm = True

            return self._model_manager

    @property
    def local_model_manager(self) -> LLMModelManager:
        """Return a model manager forced into local execution mode."""
        manager = LLMModelManager()
        manager.llm_settings.use_local_llm = True
        manager.llm_settings.use_openrouter = False
        manager.llm_settings.use_ollama = False
        return manager

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------

    def on_llm_load_model_signal(self, data: Dict) -> None:
        """Handle a queued model-load request."""
        self._load_llm_thread(data)

    def on_llm_on_unload_signal(self, data: Optional[Dict] = None) -> None:
        """Handle a queued unload request."""
        self.unload_llm(data)

    def start_worker_thread(self) -> None:
        """Start the worker thread and background model load."""
        if self.application_settings.llm_enabled or AIRUNNER_LLM_ON:
            self._load_llm_thread()

    def load(self) -> None:
        """Load the LLM model synchronously (ambient tenant context)."""
        self._load_llm()

    def unload(self, data: Optional[Dict] = None) -> None:
        """Unload the LLM model and free its resources."""
        self.unload_llm(data)

    def unload_llm(self, data: Optional[Dict] = None) -> None:
        """Unload the LLM model and execute an optional callback."""
        if not self._model_manager:
            return
        data = data or {}
        self._model_manager.unload()
        callback = data.get("callback", None)
        if callback:
            callback(data)

    def on_section_changed_signal(self, data: Dict = None) -> None:
        """Forward section changes to the model manager."""
        self.model_manager.on_section_changed()

    # ------------------------------------------------------------------
    # Inactivity timer
    # ------------------------------------------------------------------

    def _update_activity_timestamp(self) -> None:
        """Refresh the last-request timestamp for inactivity tracking."""
        self._last_request_time = time.time()

    def _start_inactivity_timer(self) -> None:
        """Start the inactivity monitoring timer when auto-unload is on."""
        if not self._auto_unload_enabled:
            return
        self._inactivity_timer = QTimer()
        self._inactivity_timer.timeout.connect(self._check_inactivity)
        self._inactivity_timer.start(60000)
        self.logger.info(
            "LLM auto-unload timer started (5 minute timeout)",
        )

    def _check_inactivity(self) -> None:
        """Unload the model after extended inactivity when enabled."""
        if not self._auto_unload_enabled or not self._last_request_time:
            return
        if not self._model_manager or not self.has_model_manager:
            return
        if (
            self._model_manager.model_status.get(ModelType.LLM)
            != ModelStatus.LOADED
        ):
            return
        inactive_time = time.time() - self._last_request_time
        if inactive_time >= self._inactivity_timeout:
            self.logger.info(
                "LLM model idle for %d minutes - auto-unloading",
                int(inactive_time / 60),
            )
            self.unload_llm()
            self._last_request_time = None

    # ------------------------------------------------------------------
    # Threaded load helpers
    # ------------------------------------------------------------------

    def _load_llm_thread(self, data: Optional[Dict] = None) -> None:
        """Load the LLM in a separate background thread."""
        from airunner_services.data.tenant import get_tenant_key

        tenant_key = get_tenant_key()
        self._llm_thread = threading.Thread(
            target=self._load_llm_in_tenant,
            args=(data, tenant_key),
        )
        self._llm_thread.start()

    def _load_llm_in_tenant(
        self,
        data: Optional[Dict],
        tenant_key: Optional[str],
    ) -> None:
        """Run the threaded model load under the captured tenant context."""
        from airunner_services.data.tenant import tenant_scope

        with tenant_scope(tenant_key):
            self._load_llm(data)

    def _load_llm(self, data: Optional[Dict] = None) -> None:
        """Load the LLM model and execute an optional callback."""
        data = data or {}
        self.model_manager.load()
        callback = data.get("callback", None)
        if callback:
            callback(data)
