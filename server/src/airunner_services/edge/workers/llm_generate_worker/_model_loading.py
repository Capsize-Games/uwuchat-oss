"""Model load / unload and threaded tenant-aware loading.

``LLMGenerateWorkerModelLoadingMixin`` owns model load/unload, the
threaded load that re-applies the captured tenant context, and the
model-changed / worker-start hooks.
"""

from __future__ import annotations

import threading
from typing import Dict, Optional

from airunner_services.settings import AIRUNNER_LLM_ON


class LLMGenerateWorkerModelLoadingMixin:
    """Model lifecycle: load, unload, and worker start."""

    def on_llm_model_changed_signal(self, data: Dict) -> None:
        """Unload only when a model change explicitly requests reload."""
        if not isinstance(data, dict) or not data.get("reload_runtime"):
            return

        if self._model_manager:
            self._model_manager.unload()

    def on_llm_on_unload_signal(self, data: Optional[Dict] = None) -> None:
        """Handle one queued unload request."""
        self.unload_llm(data)

    def on_llm_load_model_signal(self, data: Dict) -> None:
        """Handle a queued model-load request."""
        self._load_llm_thread(data)

    def start_worker_thread(self) -> None:
        """Start the worker thread if LLM is enabled."""
        if self.application_settings.llm_enabled or AIRUNNER_LLM_ON:
            self._load_llm_thread()

    def _load_llm_thread(self, data: Optional[Dict] = None) -> None:
        """Load the LLM in a separate background thread.

        A raw thread does NOT inherit the caller's tenant contextvar, so the
        model load (which reads per-tenant model_path / generator settings)
        would otherwise run against tenant_anonymous and fail with
        "No model path configured". Capture the tenant on the calling thread
        (which is in tenant context — e.g. the image-generation reload) and
        re-apply it inside the worker thread.
        """
        from airunner_services.data.tenant import get_tenant_key

        tenant_key = get_tenant_key()
        self._llm_thread = threading.Thread(
            target=self._load_llm_in_tenant,
            args=(data, tenant_key),
        )
        self._llm_thread.start()

    def _load_llm_in_tenant(
        self, data: Optional[Dict], tenant_key: Optional[str]
    ) -> None:
        """Run the threaded model load under the captured tenant context."""
        from airunner_services.data.tenant import tenant_scope

        with tenant_scope(tenant_key):
            self._load_llm(data)

    def load(self) -> None:
        """Load the LLM model synchronously (ambient tenant context)."""
        self._load_llm()

    def _load_llm(self, data: Optional[Dict] = None) -> None:
        """Load the LLM model and execute an optional callback."""
        data = data or {}
        self.model_manager.load()
        callback = data.get("callback", None)
        if callback:
            callback(data)

    def unload_llm(self, data: Optional[Dict] = None) -> None:
        """Unload the LLM model and execute an optional callback."""
        if not self._model_manager:
            return
        data = data or {}
        self._model_manager.unload()
        callback = data.get("callback", None)
        if callback:
            callback(data)

    def unload(self, data: Optional[Dict] = None) -> None:
        """Unload the LLM model and free its resources."""
        self.unload_llm(data)
