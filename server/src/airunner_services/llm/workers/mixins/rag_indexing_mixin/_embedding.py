"""Embedding-model loading for RAG indexing."""

import threading


class RAGEmbeddingMixin:
    """Load the RAG embedding model from worker signals."""

    def _ensure_embedding_loaded(self) -> None:
        """Load the RAG embedding model so its status is broadcast.

        Accessing the embedding triggers ``_emit_embedding_status`` which
        bridges to the Model Resources panel via
        ``MODEL_STATUS_CHANGED_SIGNAL``.
        """
        agent = getattr(self.model_manager, "agent", None) or self.model_manager
        try:
            # Accessing the embedding property loads the model when it is
            # not already loaded and emits its load status (which the Model
            # Resources panel listens for via MODEL_STATUS_CHANGED_SIGNAL).
            _ = getattr(agent, "embedding", None)
            setup = getattr(agent, "_setup_rag", None)
            if callable(setup):
                setup()
        except Exception as exc:
            self.logger.warning("Embedding pre-load failed: %s", exc)

    def on_rag_load_embedding_signal(
        self,
        data: dict | None = None,
    ) -> None:
        """Load the RAG embedding model on a background thread.

        Triggered by the Model Resources panel's embedding "load" button.
        """
        self.logger.info("Received RAG_LOAD_EMBEDDING signal")
        thread = threading.Thread(target=self._load_embedding_thread)
        thread.start()

    def _load_embedding_thread(self) -> None:
        """Ensure the model manager exists, then load the embedding."""
        try:
            if not self._ensure_agent_loaded("embedding"):
                return
            self._ensure_embedding_loaded()
        except Exception:
            self.logger.exception("Failed to load embedding model")
