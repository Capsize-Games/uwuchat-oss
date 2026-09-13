"""RAG document loading for the LLM generation worker.

``LLMGenerateWorkerRagMixin`` owns the RAG document signal and the
per-shape document loading helpers used by the RAG indexer.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from airunner_services.edge.model_management.llm_model_manager import (
    LLMModelManager,
)


def _load_path_document(manager: LLMModelManager, doc: Any) -> bool:
    """Load a filesystem path document into RAG."""
    if not (isinstance(doc, str) and os.path.exists(doc)):
        return False
    manager.load_file_into_rag(doc)
    return True


def _load_bytes_document(manager: LLMModelManager, doc: Any) -> bool:
    """Load a bytes/bytearray document into RAG."""
    if not isinstance(doc, (bytes, bytearray)):
        return False
    manager.load_bytes_into_rag(
        doc,
        source_name="upload",
        file_ext=".epub",
    )
    return True


def _load_content_document(manager: LLMModelManager, doc: Any) -> bool:
    """Load a dict ``content`` document into RAG by declared file type."""
    if not (isinstance(doc, dict) and "content" in doc):
        return False
    file_type = doc.get("file_type", "")
    content = doc.get("content")
    if file_type.lower() in [".html", "html"]:
        manager.load_file_into_rag(
            content,
            source_name=doc.get(
                "source_name",
                "web_content",
            ),
        )
    elif file_type.lower() in [
        ".epub",
        "epub",
        ".mobi",
        "mobi",
        ".pdf",
        "pdf",
    ]:
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
            source_name=doc.get(
                "source_name",
                "web_content",
            ),
        )
    return True


def _load_html_string_document(manager: LLMModelManager, doc: Any) -> bool:
    """Load a long HTML string document into RAG."""
    if not (
        isinstance(doc, str)
        and (
            "<html" in doc.lower()
            or "<body" in doc.lower()
            or len(doc) > 100
        )
    ):
        return False
    manager.load_html_into_rag(doc)
    return True


class LLMGenerateWorkerRagMixin:
    """RAG document signal handling and per-shape loading."""

    def on_rag_load_documents_signal(self, data: Dict) -> None:
        """Load one document batch into the RAG engine."""
        self.logger.debug("Worker received RAG signal!")
        manager = self.model_manager
        self.logger.debug(
            f"Model manager ready (type: {type(manager).__name__})"
        )

        if data.get("clear_documents", False):
            self.logger.debug("Clearing RAG documents")
            self._clear_rag_documents()

        documents = data.get("documents", [])
        if documents:
            self.logger.debug(
                f"Loading {len(documents)} documents into RAG"
            )
            self._load_documents_into_rag(documents)
            self.logger.info(
                f"✓ Loaded {len(documents)} documents into RAG"
            )

    def _clear_rag_documents(self) -> None:
        """Clear all previously indexed RAG documents."""
        if hasattr(self.model_manager, "clear_rag_documents"):
            self.model_manager.clear_rag_documents()

    def _load_documents_into_rag(self, documents: list) -> None:
        """Load one iterable of documents into the RAG engine."""
        for doc in documents:
            try:
                if _load_path_document(self.model_manager, doc):
                    continue

                if _load_bytes_document(self.model_manager, doc):
                    continue

                if _load_content_document(self.model_manager, doc):
                    continue

                if _load_html_string_document(self.model_manager, doc):
                    continue

                self.model_manager.load_html_into_rag(str(doc))
            except Exception as error:
                self.logger.error(
                    f"Failed to load RAG document {repr(doc)}: {error}"
                )
