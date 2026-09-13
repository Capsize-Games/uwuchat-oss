"""Tests for conversation inspector route helpers and flow reconstruction.

Validates the migrated patterns that use ManagedQuery and TransactionHandle.
"""

from __future__ import annotations

import pytest


class TestListConversationSummaries:
    """The _list_conversation_summaries helper from routes.py."""

    def _list_conversation_summaries(self, q, offset, limit):
        """Replicate the helper function from routes.py."""
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        # Pattern from the migrated route
        builder = Conversation.objects.query().order_by(
            Conversation.created_at.desc(),
        )
        if q:
            search = f"%{q}%"
            builder = builder.filter(
                (Conversation.title.ilike(search))
                | (Conversation.user_name.ilike(search)),
            )
        rows = builder.offset(offset).limit(limit).all()

        results = []
        for conv in rows:
            msg_count = len(conv.value) if isinstance(conv.value, list) else 0
            results.append(
                {
                    "id": conv.id,
                    "title": conv.title,
                    "user_name": conv.user_name or "Unknown",
                    "chatbot_name": conv.chatbot_name or "Unknown",
                    "message_count": msg_count,
                    "created_at": (
                        conv.created_at.isoformat()
                        if conv.created_at
                        else None
                    ),
                    "updated_at": (
                        conv.updated_at.isoformat()
                        if conv.updated_at
                        else None
                    ),
                }
            )
        return results

    def test_no_search_returns_list(self):
        """Empty query returns list (possibly empty)."""
        results = self._list_conversation_summaries("", 0, 10)
        assert isinstance(results, list)

    def test_search_filters_results(self):
        """Search term produces filtered results."""
        results = self._list_conversation_summaries(
            "nonexistent_search_xyz",
            0,
            10,
        )
        assert isinstance(results, list)
        assert len(results) == 0


class TestFlowReconstructionPattern:
    """The flow endpoint pattern from routes.py."""

    def test_flow_query_single_conversation(self):
        """Query a conversation by id (flow endpoint)."""
        from airunner_services.database.models.conversation import (
            Conversation,
        )

        conv = Conversation.objects.query().limit(1).first()
        if conv is None:
            pytest.skip("No conversations in database")

        # The flow endpoint pattern
        found = (
            Conversation.objects.query()
            .filter(Conversation.id == conv.id)
            .first()
        )
        assert found is not None
        assert found.id == conv.id
        # Dataclass attribute access — no DetachedInstanceError
        assert isinstance(found.title, (str, type(None)))

    def test_reconstruct_flow_on_real_conversation(self):
        """Call reconstruct_flow on an existing conversation."""
        from airunner_services.database.models.conversation import (
            Conversation,
        )
        from extensions.conversation_inspector.server.flow_reconstructor import (
            reconstruct_flow,
        )

        conv = Conversation.objects.query().limit(1).first()
        if conv is None:
            pytest.skip("No conversations in database")

        flow_data = reconstruct_flow(conv)
        assert isinstance(flow_data, dict)
        assert "conversation_id" in flow_data
        assert "turns" in flow_data
        assert flow_data["conversation_id"] == conv.id


class TestChatbotLookupPattern:
    """The get_chatbot_for_conversation pattern."""

    def test_chatbot_lookup_on_conversation(self):
        """Look up chatbot for an existing conversation."""
        from airunner_services.database.models.conversation import (
            Conversation,
        )
        from extensions.conversation_inspector.server.flow_reconstructor import (
            get_chatbot_for_conversation,
        )

        conv = Conversation.objects.query().limit(1).first()
        if conv is None:
            pytest.skip("No conversations in database")

        chatbot = get_chatbot_for_conversation(conv)
        if conv.chatbot_id is not None:
            assert chatbot is not None
            assert chatbot.id == conv.chatbot_id


class TestKnowledgeBaseSearchPattern:
    """The _search_knowledge_base pattern from rag_tools_helpers."""

    def test_transaction_for_search(self):
        """Use transaction pattern for knowledge base search."""
        from airunner_services.database.models.document import Document

        with Document.objects.transaction() as tx:
            docs = tx.query(Document).filter_by(active=True).limit(5).all()
            assert isinstance(docs, list)
