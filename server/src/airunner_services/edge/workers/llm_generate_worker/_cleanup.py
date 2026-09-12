"""Shutdown lifecycle for the LLM generation worker.

``LLMGenerateWorkerCleanupMixin`` owns the application-quit signal
handler that unloads the model and joins the loader thread.
"""

from __future__ import annotations

from typing import Dict, Optional


class LLMGenerateWorkerCleanupMixin:
    """Application shutdown handling."""

    def on_quit_application_signal(
        self, data: Optional[Dict] = None
    ) -> None:
        """Unload the model and stop the worker during application shutdown."""
        self.logger.debug("Quitting LLM")
        self.running = False
        if self._model_manager:
            self._model_manager.unload()
        if self._llm_thread is not None:
            self._llm_thread.join()
