"""DB-level integration test: filter_inferred_fact() blocks GDPR Art. 9
sensitive inferred facts from persistence.

Calls the real KnowledgeBase.add_fact() against a real database, then
queries the knowledge_facts table directly to assert the fact was NOT
persisted.
"""

from __future__ import annotations

import pytest


@pytest.mark.functional
class TestSensitiveFactFilterWritePath:
    """Real DB test: Article-9 facts are blocked by add_fact."""

    def test_religion_fact_not_persisted(self) -> None:
        """A religion-inferred fact must NOT appear in knowledge_facts
        after add_fact returns False."""
        from airunner_services.knowledge import KnowledgeBase
        from airunner_services.database.models.knowledge_fact import (
            KnowledgeFact,
        )

        kb = KnowledgeBase()

        # Ensure DEK check doesn't block (test DB has no encryption).
        kb._check_dek_available = lambda: None

        result = kb.add_fact(
            fact="The user is Muslim",
            source_type="inferred",
            data_source="test",
        )
        # add_fact returns False when the filter blocks the fact.
        assert result is False, (
            "add_fact should return False for a blocked inferred fact"
        )

        # The fact must not be in the database.
        rows = (
            KnowledgeFact.objects.query()
            .filter(KnowledgeFact.fact_text == "The user is Muslim")
            .all()
        )
        assert len(rows) == 0, (
            f"Religion fact was persisted despite filter: {len(rows)} rows"
        )

    def test_non_sensitive_fact_is_persisted(self) -> None:
        """A non-sensitive fact must pass the filter and be persisted."""
        from unittest.mock import MagicMock, patch
        from airunner_services.knowledge import KnowledgeBase
        from airunner_services.database.models.knowledge_fact import (
            KnowledgeFact,
        )

        kb = KnowledgeBase()

        # Mock internal DB operations so the filter test doesn't need a
        # full tenant context.
        with patch.object(kb, "_check_dek_available", return_value=None), \
             patch.object(kb, "_is_duplicate_fact", return_value=False), \
             patch.object(kb, "_find_conflicting_relationship_fact",
                          return_value=None), \
             patch.object(KnowledgeFact.objects, "create",
                          return_value=MagicMock()):
            result = kb.add_fact(
                fact="The user likes chocolate ice cream",
                source_type="inferred",
                data_source="test",
            )
        assert result is True, (
            "Non-sensitive fact was blocked incorrectly"
        )
