"""Shared model-manager configuration for the LLM generation worker.

``LLMGenerateWorkerModelManagerMixin`` owns the lazily-created model
manager and its provider/backend configuration.
"""

from __future__ import annotations

from airunner_services.edge.model_management.llm_model_manager import (
    LLMModelManager,
)


class LLMGenerateWorkerModelManagerMixin:
    """Lazy model-manager creation and provider configuration."""

    @property
    def model_manager(self) -> LLMModelManager:
        """Return the shared model manager configured for the active backend."""
        with self._model_manager_lock:
            if self._model_manager is None:
                self._model_manager = LLMModelManager()

                # LLMModelManager.__init__ already applied the project model
                # router (DIALOGUE) when AIRUNNER_PROJECT is set and the
                # routing module exists.  If a DIALOGUE rule is active, honour
                # it; otherwise fall back to the DB-level model_service setting.
                router = getattr(self._model_manager, "_model_router", None)
                if router is not None and router.rule("DIALOGUE"):
                    pass
                else:
                    db_api_key = (
                        getattr(self.llm_generator_settings, "api_key", None)
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
