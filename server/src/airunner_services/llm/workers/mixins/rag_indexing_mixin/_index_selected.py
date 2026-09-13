"""Selected-documents RAG indexing flow."""

import threading

from airunner_services.database.models.document import Document as DBDocument
from airunner_services.llm.workers.mixins.rag_indexing_mixin._base import (
    SignalCode,
)
from airunner_services.llm.workers.rag_index_status import (
    rag_index_status_tracker,
)


class RAGIndexSelectedMixin:
    """Handle RAG indexing of user-selected documents."""

    def on_rag_index_selected_documents_signal(self, data: dict) -> None:
        """Start indexing selected documents on a background thread.

        Fixes the missing-``tenant_scope`` bug: captures ``tenant_key``
        and passes it to the thread target which enters
        ``tenant_scope(tenant_key)`` before querying.  The old code
        spawned the thread without capturing ``tenant_key``, so
        ``session_scope`` would fall through to the wrong schema.
        """
        file_paths = data.get("file_paths", [])
        if not file_paths:
            self.logger.warning(
                "RAG_INDEX_SELECTED_DOCUMENTS called with no file paths"
            )
            return
        rag_index_status_tracker.start(
            total=len(file_paths),
            message="Preparing to index documents...",
        )
        self.logger.info(
            "Received RAG_INDEX_SELECTED_DOCUMENTS signal for "
            f"{len(file_paths)} documents"
        )

        from airunner_services.data.tenant import get_tenant_key

        tenant_key = get_tenant_key()

        indexing_thread = threading.Thread(
            target=self._index_selected_documents_thread,
            args=(file_paths, tenant_key),
        )
        indexing_thread.start()

    def _index_selected_documents_thread(
        self,
        file_paths: list[str],
        tenant_key: str,
    ) -> None:
        """Run selective indexing inside the correct tenant scope."""
        from airunner_services.data.tenant import tenant_scope

        with tenant_scope(tenant_key):
            if not self._ensure_agent_loaded():
                return

            if not self._validate_indexing_support():
                return

            self._index_documents(file_paths)

    def _index_documents(self, file_paths: list[str]) -> None:
        """Index one list of validated document paths."""
        total = len(file_paths)
        indexed_total = 0
        for idx, file_path in enumerate(file_paths):
            self._emit_indexing_progress(idx, total)
            validated_path = self._validate_document_path(file_path)
            if not validated_path:
                continue
            indexed_total += 1
            self._index_single_file(validated_path, idx, total)

        self.emit_signal(
            SignalCode.RAG_INDEXING_COMPLETE,
            {
                "success": True,
                "message": f"Indexed {indexed_total} of {total} documents",
            },
        )

    def _emit_indexing_progress(self, idx: int, total: int) -> None:
        """Emit one indexing progress update."""
        self.emit_signal(
            SignalCode.RAG_INDEXING_PROGRESS,
            {
                "current": idx,
                "total": total,
                "progress": int((idx / total) * 100),
            },
        )

    def _index_single_file(self, file_path: str, idx: int, total: int) -> None:
        """Index one document file by path."""
        try:
            db_doc = self._get_document_from_db(file_path)
            if not db_doc:
                return

            self.logger.info(f"Indexing document {idx + 1}/{total}: {file_path}")
            agent = getattr(self.model_manager, "agent", None) or self.model_manager
            success = agent._index_single_document(db_doc)

            if success:
                DBDocument.objects.update(pk=db_doc.id, active=True)
                self.emit_signal(
                    SignalCode.DOCUMENT_INDEXED,
                    {"path": file_path},
                )
            else:
                self._emit_index_failed(
                    file_path,
                    "No content could be extracted",
                )

        except Exception as exc:
            self.logger.error(f"Failed to index {file_path}: {exc}")
            self._emit_index_failed(file_path, str(exc))
