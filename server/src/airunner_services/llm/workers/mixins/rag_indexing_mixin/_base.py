"""Shared helpers and constants for RAG indexing signal handlers.

``RAGIndexingBase`` hosts the cross-cutting pieces used by every
indexing flow: agent/manager readiness checks, error emission, and
the document-record lookup helpers shared by the selected-documents
and single-document paths.  The ``SignalCode`` proxy and
``_DOCUMENT_FILE_SUFFIXES`` allow-list live here too so the other
submodules can import them without creating circular imports.
"""

from airunner_services.database.models.document import Document as DBDocument
from airunner_services.utils.application.enum_resolver import signal_code_proxy

_DOCUMENT_FILE_SUFFIXES = (
    ".md",
    ".txt",
    ".docx",
    ".doc",
    ".odt",
    ".pdf",
    ".epub",
    ".zim",
)

SignalCode = signal_code_proxy(
    {
        "DOCUMENT_INDEXED": "document_indexed_signal",
        "DOCUMENT_INDEX_FAILED": "document_index_failed_signal",
        "RAG_INDEXING_PROGRESS": "rag_indexing_progress_signal",
        "RAG_INDEXING_COMPLETE": "rag_indexing_complete_signal",
    }
)


class RAGIndexingBase:
    """Shared helpers for all RAG indexing signal handlers."""

    def _ensure_agent_loaded(self, operation: str = "operation") -> bool:
        """Ensure the model manager or its agent can perform indexing."""
        if self.model_manager and (
            getattr(self.model_manager, "agent", None)
            or hasattr(self.model_manager, "index_all_documents")
        ):
            return True

        self.logger.info(f"Loading LLM for {operation}...")
        try:
            self.load()
        except Exception as exc:
            self.logger.error(f"Failed to load LLM for {operation}: {exc}")
            self._emit_indexing_error(f"Failed to load LLM: {exc!s}")
            return False

        if not self.model_manager or (
            not getattr(self.model_manager, "agent", None)
            and not hasattr(self.model_manager, "index_all_documents")
        ):
            self.logger.error("Model manager loaded but agent is still None")
            self._emit_indexing_error("LLM agent not available after loading")
            return False

        return True

    def _validate_agent_supports_indexing(self) -> bool:
        """Return whether the active agent or manager supports full indexing."""
        agent = getattr(self.model_manager, "agent", None) or self.model_manager
        if not hasattr(agent, "index_all_documents"):
            self.logger.error("Agent/manager does not support manual indexing")
            self._emit_indexing_error("Agent does not support indexing")
            return False
        return True

    def _validate_indexing_support(self) -> bool:
        """Return whether the active agent supports single-document indexing."""
        agent = getattr(self.model_manager, "agent", None) or self.model_manager
        if not hasattr(agent, "_index_single_document"):
            self.logger.error("Agent/manager does not support document indexing")
            self._emit_indexing_error("Agent does not support indexing")
            return False
        return True

    def _emit_indexing_error(self, message: str) -> None:
        """Emit the shared indexing error payload."""
        self.emit_signal(
            SignalCode.RAG_INDEXING_COMPLETE,
            {"success": False, "message": message},
        )

    def _get_document_from_db(self, file_path: str):
        """Return the document record matching one file path."""
        db_docs = DBDocument.objects.filter_by(path=file_path)
        if not db_docs or len(db_docs) == 0:
            self.logger.warning(f"Document not found in database: {file_path}")
            self._emit_index_failed(
                file_path,
                "Document not found in database",
            )
            return None
        return db_docs[0]

    def _emit_index_failed(self, path: str, error: str) -> None:
        """Emit one single-document indexing failure."""
        self.emit_signal(
            SignalCode.DOCUMENT_INDEX_FAILED,
            {"path": path, "error": error},
        )
