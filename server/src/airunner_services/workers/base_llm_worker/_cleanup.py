"""Worker shutdown lifecycle.

``BaseLLMWorkerCleanupMixin`` owns the quit-application handler that
unloads the model and joins the worker thread during shutdown.
"""

from __future__ import annotations

from typing import Dict, Optional


class BaseLLMWorkerCleanupMixin:
    """Shutdown behavior for the base LLM worker."""

    def on_quit_application_signal(self, data: Optional[Dict] = None) -> None:
        """Unload the model and stop the worker during shutdown."""
        self.logger.debug("Quitting LLM")
        self.running = False
        if self._model_manager:
            self._model_manager.unload()
        if self._llm_thread is not None:
            self._llm_thread.join()
