"""Full index-all-documents RAG indexing flow."""

import threading

from airunner_services.llm.workers.rag_index_status import (
    rag_index_status_tracker,
)


class RAGIndexAllMixin:
    """Handle full RAG index-all requests for the LLM worker."""

    def on_rag_index_all_documents_signal(self, data: dict) -> None:
        """Start indexing all documents on a background thread.

        RAG indexing requires in-process access to ``model_manager``
        and is kept on a raw thread (not Celery) per the plan's
        "already-correctly-bounded in-request thread pools" rule.
        """
        force = bool(data.get("force", False)) if data else False
        self.logger.info("Received RAG_INDEX_ALL_DOCUMENTS signal (force=%s)", force)
        from airunner_services.data.tenant import get_tenant_key

        tenant_key = get_tenant_key()
        self.logger.debug("Captured tenant context for indexing")
        rag_index_status_tracker.start(
            message="Preparing to index documents...",
        )
        indexing_thread = threading.Thread(
            target=self._index_all_documents_thread,
            args=(data, force, tenant_key),
        )
        indexing_thread.start()

    def _index_all_documents_thread(
        self,
        data: dict,
        force: bool = False,
        tenant_key: str | None = None,
    ) -> None:
        """Run full-document indexing without blocking the caller.

        Any unexpected failure here (e.g. while constructing the model
        manager) must still emit a terminal signal, otherwise the
        frontend progress bar hangs on its indeterminate animation
        forever with no way to recover.

        Args:
            data: Signal payload dictionary.
            force: If True, re-index all documents regardless of status.
            tenant_key: Active tenant key captured from the caller's
                context so the database queries target the correct schema.
        """
        from airunner_services.data.tenant import tenant_scope

        with tenant_scope(tenant_key):
            self._run_index_all_documents(data, force)

    def _run_index_all_documents(
        self,
        data: dict,
        force: bool = False,
    ) -> None:
        """Execute the indexing work inside the correct tenant scope.

        Args:
            data: Signal payload dictionary.
            force: If True, re-index all documents regardless of status.
        """
        try:
            if not self._ensure_agent_loaded("indexing"):
                return

            if not self._validate_agent_supports_indexing():
                return

            # Eagerly load the embedding model so its status/VRAM are
            # reported even when there are no documents to index yet.
            self._ensure_embedding_loaded()

            self._perform_all_documents_indexing(force=force)
        except Exception as exc:
            self.logger.exception("Unexpected error during index-all")
            self._emit_indexing_error(f"Indexing failed: {exc}")

    def _perform_all_documents_indexing(
        self,
        force: bool = False,
    ) -> None:
        """Invoke full-document indexing on the active agent or manager.

        Args:
            force: If True, re-index all documents regardless of status.
        """
        self.logger.info("Starting manual document indexing with loaded agent")
        try:
            agent = getattr(self.model_manager, "agent", None) or self.model_manager
            agent.index_all_documents(force=force)
        except Exception as exc:
            self.logger.error(f"Error during indexing: {exc}")
            self._emit_indexing_error(f"Indexing error: {exc!s}")
