"""Tests for cross-turn append/cap/eviction in tool_filtering_mixin.

Covers: append-only tool selection, LRU eviction when cap is exceeded,
always-keep protection, recency-based eviction ordering, and
conversation-switch reset.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestAppendToolsWithCap:
    """Tests for _append_tools_with_cap."""

    @staticmethod
    def _make_owner(
        existing_names=None,
        conversation_id: int | None = 1,
        tool_state_conv_id: int | None = 1,
    ):
        owner = MagicMock()
        owner._current_turn = 0
        owner._tool_last_used = {}
        owner._tool_state_conversation_id = tool_state_conv_id
        wm = MagicMock()
        wm._conversation_id = conversation_id
        existing_tools = []
        if existing_names:
            for name in existing_names:
                t = MagicMock()
                t.name = name
                existing_tools.append(t)
        wm._tools = existing_tools
        wm._initialize_model = MagicMock()
        owner._workflow_manager = wm
        owner._CROSS_TURN_TOOL_CAP = 6  # small for testing
        owner._ALWAYS_KEEP_TOOLS = frozenset({
            "search_tools", "list_available_tools", "update_mood",
        })
        owner.logger = MagicMock()
        return owner

    @staticmethod
    def _call(owner, new_names, **kwargs):
        from airunner_services.llm.managers.mixins.tool_filtering_mixin \
            import ToolFilteringMixin
        new_tools = []
        for name in new_names:
            t = MagicMock()
            t.name = name
            new_tools.append(t)
        ToolFilteringMixin._append_tools_with_cap(owner, new_tools, **kwargs)

    # ── append behavior ─────────────────────────────────────────

    def test_appends_new_tools(self) -> None:
        """New tools are appended to existing set."""
        owner = self._make_owner(["search_tools", "update_mood"])
        self._call(owner, ["search_news", "calculator"])
        tool_names = [
            t.name for t in owner._workflow_manager._tools
        ]
        assert tool_names == [
            "search_tools", "update_mood", "search_news", "calculator",
        ]

    def test_does_not_duplicate(self) -> None:
        """Tools already in the set are not duplicated."""
        owner = self._make_owner(["search_tools", "update_mood"])
        self._call(owner, ["search_tools", "new_tool"])
        tool_names = [
            t.name for t in owner._workflow_manager._tools
        ]
        assert tool_names == [
            "search_tools", "update_mood", "new_tool",
        ]

    def test_rebinds_model(self) -> None:
        """After appending, _initialize_model is called."""
        owner = self._make_owner(["search_tools"])
        self._call(owner, ["new_tool"])
        owner._workflow_manager._initialize_model.assert_called_once()

    # ── cap enforcement ─────────────────────────────────────────

    def test_evicts_lru_when_over_cap(self) -> None:
        """When total exceeds cap, least-recently-used tools are evicted."""
        owner = self._make_owner([
            "search_tools", "update_mood", "old_a", "old_b", "old_c",
            "recent_x",
        ])
        owner._tool_last_used = {
            "search_tools": 10, "update_mood": 10,
            "old_a": 1, "old_b": 2, "old_c": 3,
            "recent_x": 10,
        }
        owner._current_turn = 10
        self._call(owner, ["new_a", "new_b"])

        names = {t.name for t in owner._workflow_manager._tools}
        assert "search_tools" in names
        assert "update_mood" in names
        assert "recent_x" in names
        assert "new_a" in names
        assert "new_b" in names
        assert "old_a" not in names
        assert "old_b" not in names
        assert len(owner._workflow_manager._tools) == 6

    def test_always_keep_never_evicted(self) -> None:
        """Tools in _ALWAYS_KEEP_TOOLS survive even when way over cap."""
        owner = self._make_owner([
            "search_tools", "list_available_tools", "update_mood",
            "t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8",
        ])
        owner._tool_last_used = {
            "search_tools": 1,
            "list_available_tools": 1,
            "update_mood": 1,
        }
        for i in range(1, 9):
            owner._tool_last_used[f"t{i}"] = i
        owner._current_turn = 10
        self._call(owner, ["new_x"])

        names = {t.name for t in owner._workflow_manager._tools}
        assert "search_tools" in names
        assert "list_available_tools" in names
        assert "update_mood" in names
        assert "new_x" in names
        assert len(owner._workflow_manager._tools) == 6

    def test_no_eviction_when_under_cap(self) -> None:
        """When total is under cap, nothing is evicted."""
        owner = self._make_owner(["a", "b", "c"])
        self._call(owner, ["d", "e"])
        assert len(owner._workflow_manager._tools) == 5

    # ── tool usage tracking ─────────────────────────────────────

    def test_increments_turn_counter(self) -> None:
        """Each call increments _current_turn."""
        owner = self._make_owner(["a"])
        self._call(owner, ["b"])
        assert owner._current_turn == 1
        self._call(owner, ["c"])
        assert owner._current_turn == 2

    def test_records_last_used_for_new_tools(self) -> None:
        """New tools get their last_used set to current turn."""
        owner = self._make_owner(["a"])
        self._call(owner, ["b", "c"])
        assert owner._tool_last_used["b"] == 1
        assert owner._tool_last_used["c"] == 1

    # ── conversation switch reset ───────────────────────────────

    def test_resets_on_conversation_switch(self) -> None:
        """When conversation_id changes, tool state is wiped clean."""
        # Simulate conversation A with accumulated tools
        owner = self._make_owner(
            existing_names=["search_tools", "update_mood",
                            "search_news", "calculator"],
            conversation_id=1,
            tool_state_conv_id=1,
        )
        owner._tool_last_used = {
            "search_tools": 5, "update_mood": 5,
            "search_news": 3, "calculator": 4,
        }
        owner._current_turn = 5

        # Switch to conversation B
        owner._tool_state_conversation_id = 1  # already set
        owner._workflow_manager._conversation_id = 2  # changed!

        # New turn's plan for conversation B
        self._call(owner, ["search_tools", "update_mood", "new_tool"])

        # Only conversation B's tools should be present
        tool_names = [
            t.name for t in owner._workflow_manager._tools
        ]
        assert tool_names == [
            "search_tools", "update_mood", "new_tool",
        ]
        # LRU state reset
        assert owner._current_turn == 1
        assert len(owner._tool_last_used) == 3
        assert owner._tool_last_used["new_tool"] == 1
        # Tracked conversation ID updated
        assert owner._tool_state_conversation_id == 2

    def test_no_reset_on_same_conversation(self) -> None:
        """When conversation_id stays the same, tools accumulate."""
        owner = self._make_owner(
            existing_names=["search_tools", "update_mood",
                            "search_news"],
            conversation_id=1,
            tool_state_conv_id=1,
        )
        owner._tool_last_used = {
            "search_tools": 1, "update_mood": 1, "search_news": 1,
        }
        owner._current_turn = 1

        # Same conversation, new turn
        self._call(owner, ["calculator"])

        tool_names = [
            t.name for t in owner._workflow_manager._tools
        ]
        assert tool_names == [
            "search_tools", "update_mood", "search_news", "calculator",
        ]
        assert owner._current_turn == 2
        assert owner._tool_state_conversation_id == 1


class TestRecordToolUsage:
    """Tests for _record_tool_usage in tool_execution_mixin."""

    def test_records_tool_usage(self) -> None:
        """After tool execution, last_used is updated."""
        from airunner_services.llm.managers.mixins.tool_execution_mixin \
            import ToolExecutionMixin

        owner = MagicMock()
        owner._tool_last_used = {"a": 1, "b": 2}
        owner._current_turn = 3
        tool_calls = [
            {"name": "a", "id": "c1"},
            {"name": "c", "id": "c2"},
        ]
        ToolExecutionMixin._record_tool_usage(owner, tool_calls)

        assert owner._tool_last_used["a"] == 3
        assert owner._tool_last_used["c"] == 3
        assert owner._tool_last_used["b"] == 2

    def test_noop_when_no_tracking_initialized(self) -> None:
        """When _tool_last_used doesn't exist, method is a no-op."""
        from airunner_services.llm.managers.mixins.tool_execution_mixin \
            import ToolExecutionMixin

        owner = MagicMock()
        del owner._tool_last_used
        ToolExecutionMixin._record_tool_usage(owner, [
            {"name": "a", "id": "c1"},
        ])
        assert not hasattr(owner, "_tool_last_used")
