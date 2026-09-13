"""Tests for the search/research category reconciliation in
tool_filtering_mixin.py.

This covers the DIALOGUE binding path (the direct path used when the
cheap TOOL_EXECUTION stage is not active).  The cheap-stage path is
covered separately in projects/uwuchat/server/tests/.
"""

from __future__ import annotations


class TestReconcileSearchResearch:
    """Unit tests for _reconcile_search_research()."""

    @staticmethod
    def _reconcile(categories: list[str]) -> list[str]:
        """Import-under-test helper."""
        from airunner_services.llm.managers.mixins.tool_filtering_mixin \
            import _reconcile_search_research
        return _reconcile_search_research(categories)

    # ── no-op cases ─────────────────────────────────────────────

    def test_empty_list_unchanged(self) -> None:
        """Empty list returns as-is."""
        assert self._reconcile([]) == []

    def test_neither_search_nor_research_unchanged(self) -> None:
        """Categories without search or research are left alone."""
        result = self._reconcile(["system", "math"])
        assert result == ["system", "math"]

    def test_single_unrelated_category_unchanged(self) -> None:
        """A single unrelated category is left alone."""
        result = self._reconcile(["conversation"])
        assert result == ["conversation"]

    # ── search → adds research ──────────────────────────────────

    def test_search_alone_adds_research(self) -> None:
        """Selecting 'search' also brings in 'research'."""
        result = self._reconcile(["search"])
        assert "search" in result
        assert "research" in result
        assert len(result) == 2

    def test_search_with_other_categories_adds_research(self) -> None:
        """search + system → search + system + research."""
        result = self._reconcile(["search", "system", "math"])
        assert set(result) == {"search", "system", "math", "research"}
        # Original categories stay first
        assert result[0] == "search"
        assert result[1] == "system"
        assert result[2] == "math"
        assert result[3] == "research"

    # ── research → adds search ──────────────────────────────────

    def test_research_alone_adds_search(self) -> None:
        """Selecting 'research' also brings in 'search'."""
        result = self._reconcile(["research"])
        assert "search" in result
        assert "research" in result
        assert len(result) == 2

    def test_research_with_other_categories_adds_search(self) -> None:
        """research + system → research + system + search."""
        result = self._reconcile(["research", "system"])
        assert set(result) == {"search", "research", "system"}

    # ── both already present → idempotent ───────────────────────

    def test_both_already_present_is_idempotent(self) -> None:
        """When both search and research are already selected, the list
        is unchanged."""
        result = self._reconcile(["search", "research"])
        assert result == ["search", "research"]

    def test_both_with_others_is_idempotent(self) -> None:
        """When both are present alongside others, no duplicates added."""
        result = self._reconcile(["search", "research", "math", "system"])
        assert result == ["search", "research", "math", "system"]

    # ── order preservation ──────────────────────────────────────

    def test_preserves_original_order(self) -> None:
        """Original category order is preserved; appended categories
        come last."""
        result = self._reconcile(["math", "search", "system"])
        assert result == ["math", "search", "system", "research"]

    def test_research_first_order(self) -> None:
        """When research comes before other categories, search is
        appended at the end."""
        result = self._reconcile(["research", "system"])
        assert result == ["research", "system", "search"]

    # ── auto-mode search-intent path (line 173 equivalent) ──────

    def test_auto_mode_search_intent_includes_both(self) -> None:
        """When auto-mode search-intent detection sets
        selected_categories = ['search'] (line 173), reconciliation
        adds 'research' so search_fastsearch_news is also bound."""
        # This is the exact case from line 173 of the mixin:
        # selected_categories = ["search"]
        result = self._reconcile(["search"])
        assert set(result) == {"search", "research"}
