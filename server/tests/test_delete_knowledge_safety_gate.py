"""Safety-gate tests for delete_knowledge blast-radius check.

Part 11 (HIGH) — Verifies that catch-all patterns are rejected
by the dry-run count gate, and that legitimate narrow deletes
still succeed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch



def _call_delete(text: str, is_regex: bool = False) -> str:
    """Invoke delete_knowledge with controlled mocks."""
    from airunner_services.llm.tools.knowledge_tools.delete import (
        delete_knowledge,
    )
    return delete_knowledge(text=text, is_regex=is_regex, api=None)


class TestDeleteKnowledgeBlastRadius:
    """Catch-all and broad patterns must be rejected."""

    @patch("airunner_services.knowledge.get_knowledge_base")
    def test_catch_all_regex_anything(self, mock_kb: MagicMock) -> None:
        """``[\\s\\S]*`` matches everything → rejected."""
        self._set_mock_count(mock_kb, 50)
        result = _call_delete(r"[\s\S]*", is_regex=True)
        assert "would delete" in result
        assert "50" in result

    @patch("airunner_services.knowledge.get_knowledge_base")
    def test_catch_all_regex_dot_star(self, mock_kb: MagicMock) -> None:
        """``.*`` matches everything → rejected."""
        self._set_mock_count(mock_kb, 100)
        result = _call_delete(".*", is_regex=True)
        assert "would delete" in result

    @patch("airunner_services.knowledge.get_knowledge_base")
    def test_catch_all_regex_dot_one_or_more(
        self, mock_kb: MagicMock,
    ) -> None:
        """``.{1,}`` matches everything → rejected."""
        self._set_mock_count(mock_kb, 50)
        result = _call_delete(".{1,}", is_regex=True)
        assert "would delete" in result

    @patch("airunner_services.knowledge.get_knowledge_base")
    def test_catch_all_regex_dot_nl(self, mock_kb: MagicMock) -> None:
        """``(.|\\n)*`` matches everything → rejected."""
        self._set_mock_count(mock_kb, 50)
        result = _call_delete(r"(.|\n)*", is_regex=True)
        assert "would delete" in result

    @patch("airunner_services.knowledge.get_knowledge_base")
    def test_catch_all_regex_negated_char_class(
        self, mock_kb: MagicMock,
    ) -> None:
        """``[^x]*`` matches everything → rejected."""
        self._set_mock_count(mock_kb, 50)
        result = _call_delete("[^x]*", is_regex=True)
        assert "would delete" in result

    @patch("airunner_services.knowledge.get_knowledge_base")
    def test_legitimate_narrow_delete_succeeds(
        self, mock_kb: MagicMock,
    ) -> None:
        """A specific text matching 1 fact → accepted."""
        self._set_mock_count(mock_kb, 1)
        result = _call_delete("User lives in Seattle", is_regex=False)
        assert "Deleted" in result

    @patch("airunner_services.knowledge.get_knowledge_base")
    def test_legitimate_narrow_regex_succeeds(
        self, mock_kb: MagicMock,
    ) -> None:
        """A narrow regex matching 3 facts → accepted."""
        self._set_mock_count(mock_kb, 3)
        result = _call_delete(r"lived in .*", is_regex=True)
        assert "Deleted" in result

    @patch("airunner_services.knowledge.get_knowledge_base")
    def test_exactly_at_limit_succeeds(
        self, mock_kb: MagicMock,
    ) -> None:
        """Exactly 5 matches (the limit) → accepted."""
        self._set_mock_count(mock_kb, 5)
        result = _call_delete("common word", is_regex=False)
        assert "Deleted" in result

    @patch("airunner_services.knowledge.get_knowledge_base")
    def test_one_over_limit_rejected(
        self, mock_kb: MagicMock,
    ) -> None:
        """6 matches (limit+1) → rejected."""
        self._set_mock_count(mock_kb, 6)
        result = _call_delete("common word", is_regex=False)
        assert "would delete" in result

    @staticmethod
    def _set_mock_count(mock_kb: MagicMock, count: int) -> None:
        """Mock get_knowledge_base → delete_fact to return count.

        The first call (dry_run) returns count; the second call
        (real delete) returns count as well (for success-path tests).
        """
        kb = MagicMock()
        # dry_run call returns (count > 0, count)
        # real delete call also returns (count > 0, count)
        kb.delete_fact.side_effect = [
            (count > 0, count),
            (count > 0, count),
        ]
        mock_kb.return_value = kb
