"""RAG search functionality (pgvector-backed)."""

from typing import List, Optional, Any


from airunner_services.llm.managers.agent.retriever import (
    DocumentIndexRetriever,
    MultiIndexRetriever,
)


class RAGSearchMixin:
    """Search and retrieval operations for RAG system.

    Provides the main search interface used by rag_tools.py to query
    documents.  Backed by the tenant-scoped pgvector store.
    """

    def search(self, query: str, k: int = 3) -> List[Any]:
        """Search for relevant documents using the retriever.

        This is the main search method used by rag_tools.py.

        Args:
            query: Search query
            k: Number of results to return

        Returns:
            List of Document objects with page_content and metadata
        """
        if not self.retriever:
            self.logger.warning("No retriever available for search")
            return []

        try:
            results = self.retriever.retrieve(query)

            self.logger.info(
                f"Search for '{query[:100]}' returned {len(results)} results, "
                f"{sum(1 for r in results if r.page_content)} with content"
            )

            return results[:k]

        except Exception as e:
            self.logger.error("Error during search: %s", e)
            return []

    def get_document_context(
        self,
        query: str,
        document_ids: List[int],
        k: int = 5,
        *,
        chatbot_id: int | None = None,
    ) -> str:
        """Retrieve and format pgvector context for specific KB documents.

        Maps DB document ids to their chunk ``doc_id`` hashes, runs a
        tenant-scoped similarity search, and returns a formatted context
        block ready to append to the system prompt.

        Documents are filtered to only those scoped to *chatbot_id*.
        When *chatbot_id* is ``None``, only documents with a NULL
        chatbot_id are included (unscoped legacy rows).

        Args:
            query: The user's message to retrieve against.
            document_ids: DB ids of the attached knowledge-base documents.
            k: Maximum number of chunks to return.
            chatbot_id: Current chatbot for per-chatbot document scoping.

        Returns:
            Formatted context string, or "" when nothing is available.
        """
        if not document_ids or not query.strip():
            return ""

        self._setup_rag()
        if self.embedding is None:
            self.logger.warning(
                "Embedding model unavailable; cannot retrieve document context"
            )
            return ""

        from airunner_services.database.models.document import (
            Document as DBDocument,
        )
        from airunner_services.llm.managers.agent.pgvector_store import (
            PgVectorStore,
        )

        doc_ids: List[str] = []
        try:
            query_f = DBDocument.objects.filter(
                DBDocument.id.in_(list(document_ids)),
            )
            # Scope to the current chatbot; silently exclude documents
            # belonging to other chatbots or not-yet-scoped rows.
            query_f = query_f.filter(
                DBDocument.chatbot_id == chatbot_id,
            )
            for doc in query_f:
                import os

                if os.path.exists(doc.path):
                    doc_ids.append(self._generate_doc_id(doc.path))
        except Exception as exc:
            self.logger.error("Error resolving document ids: %s", exc)
            return ""

        if not doc_ids:
            return ""

        try:
            hits = PgVectorStore.similarity_search(
                query, self.embedding, k, doc_ids
            )
        except Exception as exc:
            self.logger.error("Document context retrieval failed: %s", exc)
            return ""

        if not hits:
            self.logger.info("No relevant chunks found for attached documents")
            return ""

        sections = []
        source_names: List[str] = []
        for hit in hits:
            source = hit.document.metadata.get(
                "file_name"
            ) or hit.document.metadata.get("source", "document")
            if source not in source_names:
                source_names.append(source)
            sections.append(f"--- {source} ---\n{hit.document.page_content}")

        self.logger.info(
            "Retrieved %d chunk(s) from %d attached document(s)",
            len(hits),
            len(doc_ids),
        )
        named = ", ".join(f'"{name}"' for name in source_names)
        return (
            f"The user has attached the document(s) {named} to this "
            "conversation and you DO have access to their contents. The "
            "verbatim excerpts below were retrieved from those document(s) and "
            "are the relevant parts for the user's current message. Answer the "
            "user's question directly using these excerpts as the document's "
            "content. Do NOT say you cannot see, access, or were not given the "
            "document — you have it. If the excerpts do not contain the "
            "specific detail asked for, say that the retrieved excerpts don't "
            "cover it (rather than claiming no document is attached).\n\n"
            + "\n\n".join(sections)
        )

    def get_retriever_for_query(
        self,
        query: str,
        similarity_top_k: int = 5,
        doc_ids: Optional[List[str]] = None,
    ) -> Optional[DocumentIndexRetriever]:
        """Get a retriever for a specific query, optionally doc-scoped.

        Args:
            query: The user's query
            similarity_top_k: Number of chunks to retrieve
            doc_ids: Optional list of specific document IDs to search within

        Returns:
            Configured retriever, or None if no embedding model is available
        """
        if self.embedding is None:
            self.logger.error("No embedding model available for retriever")
            return None

        try:
            retriever = DocumentIndexRetriever(
                embedding_model=self.embedding,
                similarity_top_k=similarity_top_k,
                doc_ids=doc_ids,
            )

            self.logger.debug(
                f"Created retriever with top_k={similarity_top_k}, "
                f"filtered_docs={len(doc_ids) if doc_ids else 'all'}"
            )
            return retriever

        except Exception as e:
            self.logger.error("Error creating retriever: %s", e)
            return None

    @property
    def retriever(self) -> Optional[Any]:
        """Get a retriever over the user's active documents.

        Returns:
            A ``MultiIndexRetriever`` bound to this mixin, or None if no
            embedding model is available.
        """
        if self._retriever is None:
            if self.embedding is None:
                return None
            try:
                self._retriever = MultiIndexRetriever(
                    rag_mixin=self,
                    similarity_top_k=5,
                )
            except Exception as e:
                self.logger.error(f"Error creating multi-index retriever: {e}")
        return self._retriever
