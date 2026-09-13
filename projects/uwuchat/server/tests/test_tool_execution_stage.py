"""Tests for the cheap-model tool-execution stage.

Verifies that _categories_to_run correctly reconciles the search and
research categories so that search_news (SEARCH) and
search_fastsearch_news (RESEARCH) are always available together.
"""

from __future__ import annotations


class TestCategoriesToRun:
    """Unit tests for _categories_to_run()."""

    @staticmethod
    def _categories_to_run(
        selected_categories: list[str] | None,
    ) -> set[str]:
        """Import-under-test helper (avoids module-level import issues)."""
        from projects.uwuchat.server.tool_execution_stage import (
            _categories_to_run,
        )
        return _categories_to_run(selected_categories)

    # ── basic filtering ──────────────────────────────────────────

    def test_returns_empty_for_none(self) -> None:
        """None input returns empty set."""
        assert self._categories_to_run(None) == set()

    def test_returns_empty_for_empty_list(self) -> None:
        """Empty list returns empty set."""
        assert self._categories_to_run([]) == set()

    def test_filters_out_non_cheap_categories(self) -> None:
        """Categories outside {system,math,research,search} are dropped."""
        result = self._categories_to_run(["conversation", "image"])
        assert result == set()

    def test_keeps_cheap_category_alone(self) -> None:
        """A single cheap-stage category is kept."""
        result = self._categories_to_run(["system"])
        assert result == {"system"}

        result = self._categories_to_run(["math"])
        assert result == {"math"}

    # ── search ↔ research reconciliation ─────────────────────────

    def test_search_alone_includes_research(self) -> None:
        """Selecting 'search' also brings in 'research'."""
        result = self._categories_to_run(["search"])
        assert result == {"search", "research"}

    def test_research_alone_includes_search(self) -> None:
        """Selecting 'research' also brings in 'search'."""
        result = self._categories_to_run(["research"])
        assert result == {"search", "research"}

    def test_both_search_and_research_are_idempotent(self) -> None:
        """When both are already selected, the set remains the same."""
        result = self._categories_to_run(["search", "research"])
        assert result == {"search", "research"}

    def test_search_math_also_includes_research(self) -> None:
        """Selecting search+math brings in research but not vice versa
        for math."""
        result = self._categories_to_run(["search", "math"])
        assert result == {"search", "math", "research"}

    def test_research_system_also_includes_search(self) -> None:
        """Selecting research+system brings in search."""
        result = self._categories_to_run(["research", "system"])
        assert result == {"search", "research", "system"}

    def test_non_cheap_categories_ignored_during_reconciliation(
        self,
    ) -> None:
        """Non-cheap categories like 'image' are dropped even when
        search or research is present."""
        result = self._categories_to_run(["search", "image"])
        assert result == {"search", "research"}
