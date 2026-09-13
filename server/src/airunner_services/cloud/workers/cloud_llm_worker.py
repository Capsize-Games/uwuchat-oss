"""Cloud (API-provider) LLM generation worker — OpenRouter / Ollama / OpenAI.

This worker never loads a local model; the model router (or the DB
``model_service`` column) determines which provider to use on every
request.
"""

from __future__ import annotations

from typing import Dict, Optional

from airunner_services.contract_enums import ModelService
from airunner_services.settings import AIRUNNER_LLM_ON
from airunner_services.workers.base_llm_worker import BaseLLMWorker


class CloudLLMWorker(BaseLLMWorker):
    """Orchestrate LLM requests against a cloud API provider."""

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
    # Model manager — lazy import to avoid edge/torch deps
    # ------------------------------------------------------------------

    @property
    def model_manager(self):
        """Return the shared model manager for cloud API execution."""
        from airunner_services.cloud.workers.cloud_model_manager import (
            CloudModelManager,
        )

        with self._model_manager_lock:
            if self._model_manager is None:
                self._model_manager = CloudModelManager()
                self._model_manager._signal_emitter = self
                self._configure_provider_settings()
            return self._model_manager

    def _configure_provider_settings(self) -> None:
        """Apply provider-specific settings from DB to the model manager.

        Uses the project model router (when available) to determine the
        provider.  Falls back to the model_service column for backward
        compatibility.
        """
        mgr = self._model_manager
        from airunner_services.llm.model_router import load_project_router

        router = load_project_router()
        if router and router.apply_to_settings("DIALOGUE", mgr.llm_settings):
            self.logger.info(
                "Configured provider via project router: "
                "openrouter=%s ollama=%s openai=%s local=%s",
                mgr.llm_settings.use_openrouter,
                mgr.llm_settings.use_ollama,
                mgr.llm_settings.use_openai,
                mgr.llm_settings.use_local_llm,
            )
        else:
            self.logger.info(
                "No project router; using model_service from DB: %s",
                getattr(self.llm_generator_settings, "model_service", None),
            )
            self._apply_legacy_provider_settings(mgr)
        self._apply_api_keys(mgr)

    def _apply_legacy_provider_settings(self, mgr) -> None:
        """Apply provider flags from the model_service DB column."""
        if self.use_openrouter:
            mgr.llm_settings.use_local_llm = False
            mgr.llm_settings.use_openrouter = True
        elif self.use_ollama:
            mgr.llm_settings.use_local_llm = False
            mgr.llm_settings.use_ollama = True
        elif self.use_openai:
            mgr.llm_settings.use_local_llm = False
            mgr.llm_settings.use_openai = True
        else:
            mgr.llm_settings.use_local_llm = True

    def _apply_api_keys(self, mgr) -> None:
        """Apply API keys and base URLs from DB settings."""
        db_api_key = (
            getattr(self.llm_generator_settings, "api_key", None) or None
        )
        db_api_base_url = (
            getattr(self.llm_generator_settings, "api_base_url", None)
            or None
        )
        if mgr.llm_settings.use_openrouter and db_api_key:
            mgr.llm_settings.openrouter_api_key = db_api_key
        elif mgr.llm_settings.use_ollama and db_api_base_url:
            mgr.llm_settings.ollama_base_url = db_api_base_url
        elif mgr.llm_settings.use_openai and db_api_key:
            mgr.llm_settings.openai_api_key = db_api_key

    # ------------------------------------------------------------------
    # Model lifecycle — no-ops for cloud
    # ------------------------------------------------------------------

    def on_llm_load_model_signal(self, data: Dict) -> None:
        """Cloud workers do not load local models."""
        self.logger.debug(
            "Cloud worker ignoring model-load signal (data=%r)",
            data,
        )

    def on_llm_on_unload_signal(self, data: Optional[Dict] = None) -> None:
        """Cloud workers have no local model to unload."""
        self.logger.debug(
            "Cloud worker ignoring unload signal (data=%r)",
            data,
        )

    def start_worker_thread(self) -> None:
        """Start the worker thread (no local model to preload)."""
        if self.application_settings.llm_enabled or AIRUNNER_LLM_ON:
            self.logger.info(
                "Cloud worker started — no local model preload needed",
            )
