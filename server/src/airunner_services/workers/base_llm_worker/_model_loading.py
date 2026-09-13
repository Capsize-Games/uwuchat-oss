"""Model-change and RAG document loading.

``BaseLLMWorkerModelMixin`` owns the reload-on-model-change handler
and the RAG document batch loading; the module-level helpers below
normalise one document of any accepted shape into a RAG load call.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from airunner_services.model_management.llm_model_manager import (
        LLMModelManager,
    )


class BaseLLMWorkerModelMixin:
    """Model-change and RAG loading behavior for the base worker."""

    def on_llm_model_changed_signal(self, data: Dict) -> None:
        """Unload only when a model change explicitly requests reload."""
        if not isinstance(data, dict) or not data.get("reload_runtime"):
            return
        if self._model_manager:
            self._model_manager.unload()

    def on_rag_load_documents_signal(self, data: Dict) -> None:
        """Load one document batch into the RAG engine."""
        self.logger.debug("Worker received RAG signal!")
        manager = self.model_manager
        self.logger.debug(
            "Model manager ready (type: %s)",
            type(manager).__name__,
        )
        if data.get("clear_documents", False):
            self.logger.debug("Clearing RAG documents")
            self._clear_rag_documents()
        documents = data.get("documents", [])
        if documents:
            self.logger.debug(
                "Loading %d documents into RAG",
                len(documents),
            )
            self._load_documents_into_rag(documents)
            self.logger.info(
                "Loaded %d documents into RAG",
                len(documents),
            )

    def _clear_rag_documents(self) -> None:
        """Clear all previously indexed RAG documents."""
        if hasattr(self.model_manager, "clear_rag_documents"):
            self.model_manager.clear_rag_documents()

    def _load_documents_into_rag(self, documents: list) -> None:
        """Load one iterable of documents into the RAG engine."""
        for doc in documents:
            try:
                _load_one_rag_document(self.model_manager, doc)
            except Exception as error:
                self.logger.error(
                    "Failed to load RAG document %r: %s",
                    doc,
                    error,
                )


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _load_one_rag_document(manager: LLMModelManager, doc: Any) -> None:
    """Load one document into the RAG engine (ignores errors)."""
    if _load_path_document(manager, doc):
        return
    if _load_bytes_document(manager, doc):
        return
    if _load_content_document(manager, doc):
        return
    if _load_html_string_document(manager, doc):
        return
    manager.load_html_into_rag(str(doc))


def _load_path_document(manager: LLMModelManager, doc: Any) -> bool:
    """Load a filesystem path into RAG; False when *doc* is not one."""
    if isinstance(doc, str) and os.path.exists(doc):
        manager.load_file_into_rag(doc)
        return True
    return False


def _load_bytes_document(manager: LLMModelManager, doc: Any) -> bool:
    """Load raw bytes into RAG; False when *doc* is not bytes."""
    if isinstance(doc, (bytes, bytearray)):
        manager.load_bytes_into_rag(
            doc,
            source_name="upload",
            file_ext=".epub",
        )
        return True
    return False


def _load_content_document(manager: LLMModelManager, doc: Any) -> bool:
    """Load a content-bearing dict into RAG; False otherwise."""
    if not (isinstance(doc, dict) and "content" in doc):
        return False
    file_type = doc.get("file_type", "")
    content = doc.get("content")
    if file_type.lower() in (".html", "html"):
        manager.load_file_into_rag(
            content,
            source_name=doc.get("source_name", "web_content"),
        )
    elif file_type.lower() in (
        ".epub",
        "epub",
        ".mobi",
        "mobi",
        ".pdf",
        "pdf",
    ):
        content_bytes = (
            content
            if isinstance(content, (bytes, bytearray))
            else str(content).encode("utf-8")
        )
        normalized_ext = str(file_type).lower()
        if not normalized_ext.startswith("."):
            normalized_ext = f".{normalized_ext}"
        manager.load_bytes_into_rag(
            content_bytes,
            source_name=doc.get(
                "source_name",
                f"{normalized_ext.removeprefix('.')}_upload",
            ),
            file_ext=normalized_ext,
        )
    else:
        manager.load_html_into_rag(
            str(content),
            source_name=doc.get("source_name", "web_content"),
        )
    return True


def _load_html_string_document(manager: LLMModelManager, doc: Any) -> bool:
    """Load a HTML-like string into RAG; False when *doc* is not one."""
    if isinstance(doc, str) and (
        "<html" in doc.lower() or "<body" in doc.lower() or len(doc) > 100
    ):
        manager.load_html_into_rag(doc)
        return True
    return False
