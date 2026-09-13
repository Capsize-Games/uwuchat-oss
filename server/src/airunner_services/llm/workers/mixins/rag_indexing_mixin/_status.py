"""RAG indexing status mirroring and cancellation."""

from airunner_services.llm.workers.rag_index_status import (
    rag_index_status_tracker,
)


class RAGStatusMixin:
    """Mirror RAG indexing progress into daemon status and cancel work."""

    def on_llm_reload_rag_index_signal(self) -> None:
        """Reload the active RAG index when the model manager exists."""
        if self._model_manager:
            self._model_manager.reload_rag_engine()

    def on_rag_index_cancel_signal(self, data: dict) -> None:
        """Request cancellation of one in-flight indexing operation.

        When ``data`` contains ``{"unload_embedding": True}`` the embedding
        model is unloaded directly via the agent's ``unload_rag()`` method.
        """
        rag_index_status_tracker.cancel_requested()

        if data and data.get("unload_embedding"):
            self._cancel_embedding_unload()
            return

        self._interrupt_indexing()

    def _cancel_embedding_unload(self) -> None:
        """Unload the embedding model via the agent or model manager."""
        self.logger.info("Unload embedding requested via cancel signal")
        try:
            agent = getattr(self.model_manager, "agent", None)
            if agent is not None and hasattr(agent, "unload_rag"):
                agent.unload_rag()
                self.logger.info("Embedding model unloaded via unload_rag()")
                agent._emit_embedding_status("unloaded")
                return
            if self.model_manager is not None and hasattr(
                self.model_manager,
                "unload_rag",
            ):
                self.model_manager.unload_rag()
                self.logger.info(
                    "Embedding model unloaded via model_manager.unload_rag()",
                )
                if hasattr(self.model_manager, "_emit_embedding_status"):
                    self.model_manager._emit_embedding_status("unloaded")
        except Exception as exc:
            self.logger.error(f"Error unloading embedding: {exc}")

    def _interrupt_indexing(self) -> None:
        """Set interrupt flags for any in-progress indexing operation."""
        try:
            if self.model_manager and hasattr(
                self.model_manager,
                "do_interrupt",
            ):
                try:
                    self.model_manager.do_interrupt()
                    self.logger.info("Called model_manager.do_interrupt()")
                    return
                except Exception:
                    pass

            agent_or_mgr = (
                getattr(self.model_manager, "agent", None) or self.model_manager
            )
            if agent_or_mgr and hasattr(agent_or_mgr, "do_interrupt"):
                try:
                    agent_or_mgr.do_interrupt = True
                    self.logger.info("Set agent_or_mgr.do_interrupt = True")
                except Exception:
                    pass
        except Exception as exc:
            self.logger.error(f"Error during cancel indexing: {exc}")

    def on_rag_indexing_progress_signal(self, data: dict) -> None:
        """Mirror one in-flight progress update into daemon status."""
        rag_index_status_tracker.progress(data)

    def on_rag_indexing_complete_signal(self, data: dict) -> None:
        """Mirror one terminal progress update into daemon status."""
        rag_index_status_tracker.complete(data)
