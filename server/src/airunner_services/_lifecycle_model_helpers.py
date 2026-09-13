"""Model scanning and preload helpers for CoreLifecycleService."""

from __future__ import annotations

import os
from typing import Any, Optional

from airunner_services.settings import is_cloud


class LifecycleModelHelpersMixin:
    """Model scanning, preload, and status helpers."""

    def _trigger_initial_model_scan(self) -> None:
        """Trigger initial filesystem scans for all model types."""
        if is_cloud():
            self.logger.info(
                "Cloud deployment — skipping model filesystem scan"
            )
            return
        from airunner_services.database.session import (
            is_multitenant,
        )

        if is_multitenant():
            self.logger.info(
                "Multi-tenant mode — deferring model/lora/embedding/"
                "scheduler sync to per-tenant, on-demand reads "
                "(skipping anonymous startup scan)"
            )
            return
        try:
            scanner = self.worker_manager.model_scanner_worker
            if scanner is not None and hasattr(scanner, "add_to_queue"):
                scanner.add_to_queue({"scan": True})
                self.logger.info("Initial art model scan queued")
        except Exception:
            self.logger.exception("Failed to queue initial model scan")
        self._scan_loras()
        self._scan_embeddings()
        self._seed_schedulers()

    def _seed_schedulers(self) -> None:
        """Seed the schedulers table with known SDXL and Z-Image entries."""
        from airunner_services.database.models.schedulers import (
            Schedulers,
        )
        from airunner_services.database.session import (
            session_scope,
        )
        from airunner_services.database.scan_helpers import (
            seed_schedulers,
        )

        seed_schedulers(Schedulers, session_scope)

    def _scan_loras(self) -> None:
        """Scan LoRA directories and upsert found files into the DB."""
        from airunner_services.database.models.lora import (
            Lora,
        )
        from airunner_services.database.session import (
            session_scope,
        )
        from airunner_services.database.scan_helpers import (
            scan_loras,
        )
        from airunner_services.settings import (
            AIRUNNER_BASE_PATH,
        )

        scan_loras(AIRUNNER_BASE_PATH, Lora, session_scope)

    def _scan_embeddings(self) -> None:
        """Scan embedding directories and upsert found files into the DB."""
        from airunner_services.database.models.embedding import (
            Embedding,
        )
        from airunner_services.database.session import (
            session_scope,
        )
        from airunner_services.database.scan_helpers import (
            scan_embeddings,
        )
        from airunner_services.settings import (
            AIRUNNER_BASE_PATH,
        )

        scan_embeddings(AIRUNNER_BASE_PATH, Embedding, session_scope)

    def preload_llm_model(self) -> None:
        """Preload the configured local LLM when enabled."""
        if os.environ.get("AIRUNNER_NO_PRELOAD") == "1":
            self._log_preload_disabled()
            return
        if is_cloud():
            self.logger.info("Cloud deployment — skipping LLM model preload")
            return
        self._log_preload_environment()
        model_path = self._resolve_preload_model_path()
        if not model_path:
            self.logger.info(
                "No LLM model configured - model will load on first request"
            )
            return
        self._emit_llm_load(model_path)

    def _log_preload_disabled(self) -> None:
        """Log that model preloading is disabled."""
        self.logger.info(
            "Model preloading disabled (--no-preload flag or "
            "AIRUNNER_NO_PRELOAD=1)"
        )
        self.logger.info("Models will be loaded on first request")

    def _log_preload_environment(self) -> None:
        """Log best-effort preload environment diagnostics."""
        try:
            from airunner_services.settings import (
                AIRUNNER_DB_URL,
                DEV_ENV,
            )

            self._log_debug(
                "Preload environment diagnostics: db_url_present=%s "
                "DEV_ENV=%s",
                bool(AIRUNNER_DB_URL),
                DEV_ENV,
            )
        except Exception:
            return

    def _resolve_preload_model_path(self) -> Optional[str]:
        """Resolve and persist the model path used for preload."""
        try:
            return self._preload_settings_store.resolve_model_path()
        except Exception as exc:
            self.logger.info("Warning: Could not pre-load model: %s", exc)
            self.logger.info("Model will load on first request")
            return None

    def _emit_llm_load(self, model_path: str) -> None:
        """Emit the preload signal for the resolved model path."""
        from airunner_services.contract_enums import (
            SignalCode,
        )
        from airunner_services.utils.application.log_hygiene import (
            fingerprint_value,
        )

        self._preloaded_model_path = model_path
        self.logger.info("Pre-loading LLM model")
        self._log_debug(
            "Preload signal path (%s)",
            fingerprint_value(model_path, label="model_path"),
        )
        self.logger.info("This may take 30-60 seconds...")
        self.signal_source.emit_signal(
            SignalCode.LLM_LOAD_SIGNAL,
            {"model_path": model_path},
        )
        import time

        time.sleep(5)
        self.logger.info("Model loading initiated in background")

    def _loaded_model_names(self) -> list[str]:
        """Return lifecycle-owned loaded model names for status inspection."""
        if self.worker_manager is not None:
            loaded_model_names = getattr(
                self.worker_manager,
                "loaded_model_names",
                None,
            )
            if callable(loaded_model_names):
                return loaded_model_names()
        if self.model_load_balancer is None:
            return []
        try:
            loaded = self.model_load_balancer.get_loaded_models()
        except Exception:
            return []
        return [model.name for model in loaded]

    def _log_debug(self, message: str, *args: Any) -> None:
        """Log one debug message when the injected logger supports it."""
        debug = getattr(self.logger, "debug", None)
        if callable(debug):
            debug(message, *args)
