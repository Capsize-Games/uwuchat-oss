"""Verify the email-knowledge tool wiring and the entity-relationship
lookup bug it exposed.

Context: get_memory_context() (the email-aware RAG retrieval — thread
summaries + entity facts) was fully implemented but never called from
any live prompt-assembly or tool-selection code path — confirmed by
grep, zero call sites outside its own definition. This tool is the
fix: it reuses the same retrieval logic as an on-demand,
LLM-selectable tool, matching the existing search_conversations
pattern. Wiring it up for the first time immediately surfaced a real
bug: KnowledgeBase.get_entity_relationships called the staticmethod
_safe_entity_ids unqualified (no ``self.``), which is a NameError at
runtime, not a lookup of the class's own staticmethod — never caught
because the omnipotent entity-lookup path had never actually run.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestSearchEmailKnowledgeToolRegistered:
    def test_tool_is_registered(self) -> None:
        from airunner_services.llm.core.tool_registry import ToolRegistry

        ToolRegistry._ensure_default_tools_loaded(
            required_name="search_email_knowledge",
        )
        info = ToolRegistry.get("search_email_knowledge")
        assert info is not None

    def test_module_listed_in_default_tool_reload(self) -> None:
        """Guards against silently dropping the module from the
        framework's tool-loading list (the actual registration hook
        — importing the module alone does nothing without this)."""
        import inspect

        from airunner_services.llm.core.tool_registry import ToolRegistry

        source = inspect.getsource(
            ToolRegistry._ensure_default_tools_loaded,
        )
        assert "projects.uwuchat.server.tools.email_tools" in source

    def test_context_search_uses_body_chunk_function(self) -> None:
        """Guards against the email-body-chunk migration silently
        leaving _search_email_context wired to the old, now-deleted
        search_email_summaries function name."""
        import inspect

        from airunner_services.llm.managers.prompt_builder import (
            context,
        )

        source = inspect.getsource(context._search_email_context)
        assert "search_email_body_chunks" in source
        assert "search_email_summaries" not in source


class TestSearchEmailKnowledgeGating:
    def test_non_omnipotent_chatbot_returns_gated_message(self) -> None:
        """A regular companion chatbot must not attempt any search —
        email data only ever belongs to the system bot."""
        from projects.uwuchat.server.tools.email_tools import (
            search_email_knowledge,
        )

        fn = getattr(search_email_knowledge, "func", search_email_knowledge)

        with patch(
            "projects.uwuchat.server.tools.email_tools._is_omnipotent",
            return_value=False,
        ):
            result = fn(query="anything")

        assert "system assistant" in result.lower()

    def test_empty_query_short_circuits(self) -> None:
        from projects.uwuchat.server.tools.email_tools import (
            search_email_knowledge,
        )

        fn = getattr(search_email_knowledge, "func", search_email_knowledge)
        result = fn(query="   ")
        assert "provide a topic" in result.lower()


class TestGetEntityRelationshipsSafeIdsBug:
    """Regression test for the _safe_entity_ids NameError."""

    def test_blocked_chatbots_path_does_not_raise(self) -> None:
        from airunner_services.knowledge_rag import KnowledgeBaseRAGMixin

        kb = MagicMock(spec=KnowledgeBaseRAGMixin)
        kb._blocked_chatbot_ids.return_value = [999]

        edge = MagicMock()
        edge.entity_a_id = 1
        edge.entity_b_id = 2
        edge.deleted = False

        tx = MagicMock()
        tx.query.return_value.filter.return_value.all.side_effect = [
            [edge],  # edges_raw
            [(2,)],  # Entity.id query inside _safe_entity_ids
            [MagicMock(id=2, display_name_ct="Contact")],  # entities
        ]

        with patch(
            "airunner_services.database.models.entity_relationship"
            ".EntityRelationship.objects.transaction",
        ) as mock_txn:
            mock_txn.return_value.__enter__.return_value = tx

            # Must not raise NameError: name '_safe_entity_ids' is
            # not defined.
            result = KnowledgeBaseRAGMixin.get_entity_relationships(
                kb, entity_id=1,
            )

        assert isinstance(result, list)
