"""Idle auto-unload tracking for the LLM generation worker.

``LLMGenerateWorkerInactivityMixin`` owns the inactivity timer that
auto-unloads the local model after an extended idle period.
"""

from __future__ import annotations

import time

from airunner_services.contract_enums import ModelStatus, ModelType
from airunner_services.utils.application.runtime_primitives import QTimer


class LLMGenerateWorkerInactivityMixin:
    """Inactivity timer and last-request tracking."""

    def _start_inactivity_timer(self) -> None:
        """Start the inactivity monitoring timer when auto-unload is on."""
        if not self._auto_unload_enabled:
            return

        self._inactivity_timer = QTimer()
        self._inactivity_timer.timeout.connect(self._check_inactivity)
        self._inactivity_timer.start(60000)
        self.logger.info("LLM auto-unload timer started (5 minute timeout)")

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
                f"LLM model idle for {int(inactive_time/60)} minutes - auto-unloading"
            )
            self.unload_llm()
            self._last_request_time = None

    def _update_activity_timestamp(self) -> None:
        """Refresh the last-request timestamp for inactivity tracking."""
        self._last_request_time = time.time()
