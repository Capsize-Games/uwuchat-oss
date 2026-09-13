"""Tests for category-switch cache stability (append-only semantics).

Verifies that:
1. A simulated switch_tool_category does not shrink/reorder the tools array.
2. The prebound path uses list.remove() instead of rebuilding the list.
3. The tools array hash/length is stable (only grows) across switches.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def _make_tool(name: str) -> MagicMock:
    """Return a MagicMock tool with a .name attribute."""
    t = MagicMock()
    t.name = name
    return t


class TestCategorySwitchAppendOnly:
    """Tests that _rebind_for_category uses append-only semantics."""

    @staticmethod
    def _make_owner(existing_names=None):
        """Return a mock WorkflowManager with _tools and _tool_manager."""
        owner = MagicMock()
        existing = [_make_tool(n) for n in (existing_names or [])]
        owner._tools = existing
        tm = MagicMock()
        tm.get_tools_by_categories = MagicMock(
            side_effect=_fake_get_tools_by_categories,
        )
        owner._tool_manager = tm
        owner._unbind_tools_from_model = MagicMock()
        owner._bind_tools_to_model = MagicMock()
        owner.logger = MagicMock()
        return owner

    def test_rebind_appends_not_replaces(self) -> None:
        """_rebind_for_category appends new tools; existing tools stay."""
        owner = self._make_owner(
            ["search_tools", "update_mood", "search_news"],
        )
        from airunner_services.llm.core.tool_registry import ToolCategory
        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )
        ToolExecutionMixin._rebind_for_category(
            owner, ToolCategory.KNOWLEDGE,
        )
        names = [t.name for t in owner._tools]
        assert "search_tools" in names
        assert "update_mood" in names
        assert "search_news" in names
        assert "record_knowledge" in names
        assert "recall_knowledge" in names
        assert "list_tool_categories" in names
        assert "switch_tool_category" not in names

    def test_rebind_keeps_switch_when_requested(self) -> None:
        """keep_switch=True retains switch_tool_category."""
        owner = self._make_owner(["search_tools"])
        from airunner_services.llm.core.tool_registry import ToolCategory
        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )
        ToolExecutionMixin._rebind_for_category(
            owner, ToolCategory.KNOWLEDGE, keep_switch=True,
        )
        names = [t.name for t in owner._tools]
        assert "switch_tool_category" in names

    def test_rebind_no_duplicates(self) -> None:
        """Already-present tools are not duplicated."""
        owner = self._make_owner(
            ["record_knowledge", "search_tools"],
        )
        from airunner_services.llm.core.tool_registry import ToolCategory
        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )
        ToolExecutionMixin._rebind_for_category(
            owner, ToolCategory.KNOWLEDGE,
        )
        names = [t.name for t in owner._tools]
        assert names.count("record_knowledge") == 1

    def test_prebound_path_uses_remove_not_rebuild(self) -> None:
        """The prebound path strips switch_tool_category via
        list.remove()."""
        owner = self._make_owner(
            ["search_tools", "switch_tool_category", "record_knowledge"],
        )
        owner._prebound_switch_ids = {"call_1"}
        tools_ref_before = owner._tools
        owner._unbind_tools_from_model = MagicMock()
        owner._bind_tools_to_model = MagicMock()

        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )
        tool_calls = [{
            "name": "switch_tool_category",
            "id": "call_1",
            "args": {"category": "knowledge"},
        }]
        ToolExecutionMixin._handle_category_switch(
            owner, tool_calls, {"messages": []},
        )
        # List identity must be preserved.
        assert owner._tools is tools_ref_before
        names = [t.name for t in owner._tools]
        assert "switch_tool_category" not in names
        assert "search_tools" in names
        assert "record_knowledge" in names

    def test_tools_hash_only_grows_across_category_switch(
        self,
    ) -> None:
        """Tool names/hash should not shrink after a category switch."""
        owner = self._make_owner(["search_tools", "update_mood"])
        from airunner_services.llm.core.tool_registry import ToolCategory
        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )
        names_before = set(t.name for t in owner._tools)
        ToolExecutionMixin._rebind_for_category(
            owner, ToolCategory.KNOWLEDGE,
        )
        names_after = set(t.name for t in owner._tools)
        assert names_before.issubset(names_after), (
            f"Tools lost: {names_before - names_after}"
        )
        assert len(names_after) > len(names_before)

    def test_non_prebound_removes_switch_tool_category(
        self,
    ) -> None:
        """The non-prebound success path strips switch_tool_category.

        Seeds self._tools with switch_tool_category already bound
        (simulating the state after a prebind) then calls
        _rebind_for_category(keep_switch=False) — the path taken by
        _handle_category_switch when a non-prebound
        switch_tool_category succeeds.  Verifies the tool is removed
        via list.remove() while all other tools are retained.
        """
        owner = self._make_owner(
            ["search_tools", "switch_tool_category", "update_mood"],
        )
        from airunner_services.llm.core.tool_registry import ToolCategory
        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )
        ToolExecutionMixin._rebind_for_category(
            owner, ToolCategory.KNOWLEDGE, keep_switch=False,
        )
        names = [t.name for t in owner._tools]
        assert "switch_tool_category" not in names, (
            "switch_tool_category must be removed after non-prebound success"
        )
        assert "search_tools" in names
        assert "update_mood" in names
        assert "record_knowledge" in names
        assert "recall_knowledge" in names


# ── helpers ──────────────────────────────────────────────────────

_CATEGORY_TOOLS: dict[str, list[MagicMock]] = {
    "knowledge": [
        _make_tool("record_knowledge"),
        _make_tool("recall_knowledge"),
        _make_tool("search_tools"),
    ],
    "orchestration": [
        _make_tool("list_tool_categories"),
        _make_tool("switch_tool_category"),
    ],
    "research": [
        _make_tool("search_news"),
        _make_tool("scrape_website"),
    ],
    "system": [
        _make_tool("update_mood"),
        _make_tool("get_current_datetime"),
    ],
}


def _fake_get_tools_by_categories(
    categories, include_deferred=False,
):
    """Return fake tool list for the given categories."""
    result: list[MagicMock] = []
    for cat_enum in categories:
        key = (
            cat_enum.value
            if hasattr(cat_enum, "value")
            else str(cat_enum)
        )
        result.extend(_CATEGORY_TOOLS.get(key, []))
    return result
