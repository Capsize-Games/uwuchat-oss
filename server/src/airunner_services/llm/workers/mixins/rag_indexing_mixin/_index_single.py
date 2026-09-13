"""Single-document RAG indexing flow."""

import os

from airunner_services.database.models.document import Document as DBDocument
from airunner_services.llm.workers.mixins.rag_indexing_mixin._base import (
    _DOCUMENT_FILE_SUFFIXES,
    SignalCode,
)
from airunner_services.runtimes.file_policy import (
    PathPolicyError,
    resolve_existing_file,
)


class RAGIndexSingleMixin:
    """Handle indexing of one document path from a signal payload."""

    def on_index_document_signal(self, data: dict) -> None:
        """Index a single document path from one signal payload."""
        document_path = self._validate_document_path(data.get("path", None))
        if not document_path:
            return

        filename = os.path.basename(document_path)
        self.logger.info(f"Starting indexing process for: {filename}")

        db_doc = self._get_document_from_db(document_path)
        if not db_doc:
            return

        if not self._ensure_agent_loaded():
            self._emit_index_failed(document_path, "Failed to load LLM model")
            return

        self._process_document_indexing(document_path, db_doc, filename)

    def _validate_document_path(self, path) -> str | None:
        """Validate and normalize one document path from a signal payload."""
        if not isinstance(path, str) or not path:
            self.logger.warning("INDEX_DOCUMENT signal received with invalid path")
            return None
        try:
            return resolve_existing_file(
                path,
                label="Document path",
                allowed_suffixes=_DOCUMENT_FILE_SUFFIXES,
                allowed_roots=self._allowed_document_roots(),
            )
        except PathPolicyError as error:
            self.logger.warning("Rejected document path: %s", error)
            self._emit_index_failed(path, str(error))
            return None

    def _allowed_document_roots(self) -> tuple[str, ...]:
        """Return the allowed filesystem roots for indexing requests."""
        path_settings = getattr(self, "path_settings", None)
        if path_settings is None:
            return ()
        base_path = getattr(path_settings, "base_path", "")
        documents_path = getattr(path_settings, "documents_path", "")
        roots = [documents_path]
        if base_path:
            roots.append(os.path.join(os.path.expanduser(base_path), "zim"))
        return tuple(root for root in roots if root)

    def _process_document_indexing(
        self,
        path: str,
        db_doc,
        filename: str,
    ) -> None:
        """Index one database-backed document record."""
        try:
            self.logger.info(f"Indexing document: {filename}")
            agent = getattr(self.model_manager, "agent", None) or self.model_manager
            success = agent._index_single_document(db_doc)

            if success:
                self._handle_indexing_success(path, db_doc, filename)
            else:
                self._handle_indexing_failure(path, filename)

        except Exception as exc:
            self.logger.exception(f"Failed to index document {filename}")
            self._emit_index_failed(path, str(exc))

    def _handle_indexing_success(
        self,
        path: str,
        db_doc,
        filename: str,
    ) -> None:
        """Finalize one successful document indexing operation."""
        DBDocument.objects.update(pk=db_doc.id, active=True)
        self.logger.info(f"Successfully indexed document: {filename}")
        self.emit_signal(SignalCode.DOCUMENT_INDEXED, {"path": path})

    def _handle_indexing_failure(self, path: str, filename: str) -> None:
        """Finalize one failed document indexing operation."""
        self.logger.error(f"Failed to index document: {filename}")
        self._emit_index_failed(
            path,
            "No content could be extracted from document. "
            "The file may be corrupted, empty, or in an unsupported format.",
        )
