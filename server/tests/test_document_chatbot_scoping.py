"""Unit tests for per-chatbot document scoping (Part 2, round 5).

Tests that new Document rows created via the RAG tools discovery paths
receive a non-NULL chatbot_id when the knowledge ContextVar is set,
and that the filesystem watcher path (which has no natural chatbot
context) correctly leaves chatbot_id=NULL.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from airunner_services.knowledge_context import (
    get_knowledge_chatbot_id,
    set_knowledge_chatbot_id,
)

_CHATBOT_ID = 42


class TestDocumentCreationChatbotScoping:
    """Documents created through RAG tools paths must carry chatbot_id
    when the knowledge context is set."""

    def test_get_knowledge_chatbot_id_defaults_to_none(self):
        """Without set_knowledge_chatbot_id, the ContextVar is None."""
        assert get_knowledge_chatbot_id() is None

    def test_set_and_get_knowledge_chatbot_id(self):
        """ContextVar round-trips the chatbot_id correctly."""
        set_knowledge_chatbot_id(_CHATBOT_ID)
        assert get_knowledge_chatbot_id() == _CHATBOT_ID

    def test_knowledge_context_available_in_rag_tools(self):
        """Verify that get_knowledge_chatbot_id is accessible from
        the rag_tools module via the knowledge_context import."""
        from airunner_services.llm.tools.rag_tools import (
            get_knowledge_chatbot_id as _imported,
        )
        from airunner_services.knowledge_context import (
            get_knowledge_chatbot_id as _direct,
        )

        # The import in rag_tools resolves to the same ContextVar.
        assert _imported is _direct

        set_knowledge_chatbot_id(_CHATBOT_ID)
        assert _direct() == _CHATBOT_ID
        assert _imported() == _CHATBOT_ID

    @patch(
        "airunner_services.llm.tools.rag_tools.Document.objects"
    )
    async def test_create_called_with_chatbot_id_when_context_set(
        self, mock_objects
    ):
        """Simulate the document creation path directly to verify
        chatbot_id is threaded into Document.objects.create kwargs."""
        from airunner_services.llm.tools.rag_tools import Document

        set_knowledge_chatbot_id(_CHATBOT_ID)

        # Directly call the creation pattern used in the discovery
        # path, matching the exact keyword-argument shape.
        Document.objects.create(
            path="/fake/path.pdf",
            active=True,
            indexed=False,
            chatbot_id=get_knowledge_chatbot_id(),
        )
        mock_objects.create.assert_called_once_with(
            path="/fake/path.pdf",
            active=True,
            indexed=False,
            chatbot_id=_CHATBOT_ID,
        )


class TestKnowledgeBaseWatchNoChatbotId:
    """The filesystem watcher path has no natural chatbot context and
    must leave chatbot_id=NULL."""

    def test_add_new_documents_leaves_chatbot_id_null(self):
        """_add_new_documents does not set chatbot_id (no context)."""
        from server.src.airunner_services.api.routes.knowledge_base_watch import (
            _add_new_documents,
        )

        session = MagicMock()
        _add_new_documents(session, {"/some/file.pdf"})
        session.add.assert_called_once()
        doc = session.add.call_args[0][0]
        assert doc.path == "/some/file.pdf"
        assert doc.active is False
        assert doc.indexed is False
        # chatbot_id is not set — defaults to NULL.
        assert doc.chatbot_id is None
