"""Request-time RAG preparation mixin.

Extracted from ``RequestHandlingMixin``.  Prepares attached-document
RAG for the current request (tool-hint or injection strategy),
ensures the document-search tool is exposed, and loads request-
provided RAG file payloads.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from airunner_services.llm.managers.request_rag_preparation import (
    ensure_request_rag_files,
    load_rag_document_payload,
    prepare_request_rag,
)


class RequestRagMixin:
    """RAG preparation for incoming LLM requests."""

    def _prepare_request_rag(
        self,
        data: Dict[str, Any],
        llm_request: Any,
        selected_categories: List[str],
    ) -> None:
        """Ensure request-provided or inferred RAG files are indexed."""
        del data
        prepare_request_rag(self, llm_request, selected_categories)

    @staticmethod
    def _rag_strategy() -> str:
        """Return the active RAG strategy: ``tool`` (default) or ``injection``.

        Production default is ``tool`` — the model decides when to call the
        ``rag_search`` tool, saving tokens.  Development can set
        ``AIRUNNER_RAG_STRATEGY=injection`` in ``.env`` to retrieve and inject
        document context up front (more reliable for weaker local models).
        """
        value = os.environ.get("AIRUNNER_RAG_STRATEGY", "tool")
        value = (value or "tool").strip().lower()
        return "injection" if value == "injection" else "tool"

    def _prepare_request_document_context(
        self,
        data: Dict[str, Any],
        llm_request: Any,
    ) -> None:
        """Prepare attached-document RAG for this request.

        Two strategies, selected via ``AIRUNNER_RAG_STRATEGY``:

        * ``tool`` (default): nudge the model with a short hint listing the
          attached documents and ensure the ``rag_search`` tool is available,
          letting the model decide when to retrieve.
        * ``injection``: retrieve top-k chunks now and inject their content
          into the system prompt.

        Either way the result is stored on ``self._active_rag_context`` for the
        system-prompt builder; cleared when no documents are attached.
        """
        self._active_rag_context = None
        document_ids = getattr(llm_request, "active_document_ids", None) or []
        if not document_ids:
            return

        # Resolve the current chatbot for per-chatbot document scoping.
        chatbot = getattr(self, "chatbot", None)
        chatbot_id: int | None = (
            getattr(chatbot, "id", None) if chatbot else None
        )

        if self._rag_strategy() == "injection":
            prompt = data.get("request_data", {}).get("prompt", "") or ""
            if not prompt.strip():
                return
            try:
                context = self.get_document_context(
                    prompt, document_ids, k=5,
                    chatbot_id=chatbot_id,
                )
            except Exception as exc:
                self.logger.error(
                    "Failed to build document context: %s",
                    exc,
                    exc_info=True,
                )
                return
            if context:
                self._active_rag_context = context
            return

        # Tool strategy: short hint + make the document-search tool available.
        self._active_rag_context = self._build_document_tool_hint(
            document_ids, chatbot_id=chatbot_id,
        )
        self._ensure_document_search_tool_available()

    def _build_document_tool_hint(
        self,
        document_ids: List[int],
        *,
        chatbot_id: int | None = None,
    ) -> str:
        """Return a concise system-prompt hint for tool-based document RAG.

        Documents are filtered to only those scoped to *chatbot_id*.
        When *chatbot_id* is ``None``, only documents with a NULL
        chatbot_id are included (unscoped legacy rows).
        """
        from airunner_services.database.models.document import (
            Document as DBDocument,
        )

        names: List[str] = []
        try:
            query = DBDocument.objects.filter(
                DBDocument.id.in_(list(document_ids)),
            )
            # Scope to the current chatbot; silently exclude documents
            # belonging to other chatbots or not-yet-scoped rows.
            query = query.filter(
                DBDocument.chatbot_id == chatbot_id,
            )
            for doc in query:
                names.append(os.path.basename(doc.path))
        except Exception as exc:
            self.logger.error(
                "Error resolving attached document names: %s", exc
            )

        listed = (
            ", ".join(names) if names else f"{len(document_ids)} document(s)"
        )
        return (
            f"The user has attached the following document(s) to this "
            f"conversation: {listed}. When their question may be answered from "
            f"these documents, call the `rag_search` tool to retrieve relevant "
            f"passages before answering. Only search when it is actually "
            f"relevant — do not call the tool for small talk."
        )

    def _ensure_document_search_tool_available(self) -> None:
        """Add the document-search tool to the workflow for this request."""
        if not self._workflow_manager or not self._tool_manager:
            return
        from airunner_services.llm.core.tool_registry import ToolCategory

        try:
            rag_tools = self._tool_manager.get_tools_by_categories(
                [ToolCategory.RAG],
                include_deferred=True,
            )
        except Exception as exc:
            self.logger.error("Could not resolve RAG tools: %s", exc)
            return
        if not rag_tools:
            return

        current = list(getattr(self._workflow_manager, "_tools", []) or [])
        existing_names = {
            getattr(tool, "name", getattr(tool, "__name__", None))
            for tool in current
        }
        added = [
            tool
            for tool in rag_tools
            if getattr(tool, "name", getattr(tool, "__name__", None))
            not in existing_names
        ]
        if not added:
            return
        self.logger.info(
            "[RAG] Exposing %d document-search tool(s) for attached documents",
            len(added),
        )
        self._workflow_manager.update_tools(current + added)

    def _ensure_request_rag_files(self, rag_files: Any) -> None:
        """Load and index request-provided RAG files."""
        ensure_request_rag_files(self, rag_files)

    def _load_rag_document_payload(self, doc: Dict[str, Any]) -> None:
        """Load one request-provided document payload into RAG."""
        load_rag_document_payload(self, doc)
