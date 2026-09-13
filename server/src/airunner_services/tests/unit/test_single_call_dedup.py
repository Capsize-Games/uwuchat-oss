"""Tests for _intercept_single_call_duplicates.

Verifies that duplicate single-call tools are intercepted with synthetic
ToolMessages without mutating self._tools — the critical invariant for
prompt-cache stability.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestInterceptSingleCallDuplicates:
    """Tests for the interception-based dedup logic."""

    @staticmethod
    def _make_owner(executed_tools=None):
        owner = MagicMock()
        owner._executed_tools = list(executed_tools or [])
        owner._tools = [
            MagicMock(name="update_mood"),
            MagicMock(name="search_news"),
            MagicMock(name="record_knowledge"),
        ]
        for t, n in zip(owner._tools, ["update_mood", "search_news",
                                         "record_knowledge"]):
            t.name = n
        owner.logger = MagicMock()
        owner._SINGLE_CALL_TOOLS = frozenset({
            "update_mood", "block_user", "list_available_tools",
            "get_current_datetime", "get_current_date_context",
        })
        return owner

    @staticmethod
    def _call(owner, tool_calls):
        from airunner_services.llm.managers.mixins.tool_execution_mixin \
            import ToolExecutionMixin
        return ToolExecutionMixin._intercept_single_call_duplicates(
            owner, tool_calls,
        )

    # ── happy path ──────────────────────────────────────────────

    def test_no_duplicates_passes_through(self) -> None:
        """When no single-call tool is duplicated, all calls pass."""
        owner = self._make_owner()
        tool_calls = [
            {"name": "search_news", "id": "c1"},
            {"name": "record_knowledge", "id": "c2"},
        ]
        filtered, synthetic = self._call(owner, tool_calls)
        assert filtered == tool_calls
        assert synthetic == {}

    def test_multi_call_tool_not_intercepted(self) -> None:
        """record_knowledge (multi-call) is never intercepted even if
        already executed."""
        owner = self._make_owner(executed_tools=["record_knowledge"])
        tool_calls = [
            {"name": "record_knowledge", "id": "c1"},
        ]
        filtered, synthetic = self._call(owner, tool_calls)
        assert filtered == tool_calls
        assert synthetic == {}

    # ── dedup path ──────────────────────────────────────────────

    def test_intercepts_duplicate_single_call(self) -> None:
        """A single-call tool already executed is intercepted."""
        owner = self._make_owner(executed_tools=["update_mood"])
        tool_calls = [
            {"name": "update_mood", "id": "c1"},
            {"name": "search_news", "id": "c2"},
        ]
        filtered, synthetic = self._call(owner, tool_calls)

        # Only search_news passes through
        assert filtered == [{"name": "search_news", "id": "c2"}]
        # update_mood gets a synthetic result
        assert "c1" in synthetic
        assert "already executed" in synthetic["c1"]

    def test_tools_array_unchanged(self) -> None:
        """self._tools is NOT mutated by interception."""
        owner = self._make_owner(executed_tools=["update_mood"])
        tools_before = list(owner._tools)
        self._call(owner, [{"name": "update_mood", "id": "c1"}])
        assert owner._tools == tools_before, (
            f"BUG: self._tools changed! Before={tools_before}, "
            f"After={owner._tools}"
        )

    # ── edge cases ──────────────────────────────────────────────

    def test_mixed_batch_one_dup_one_new(self) -> None:
        """Batch with one already-executed and one new single-call tool."""
        owner = self._make_owner(executed_tools=["update_mood"])
        tool_calls = [
            {"name": "update_mood", "id": "c1"},
            {"name": "list_available_tools", "id": "c2"},
        ]
        filtered, synthetic = self._call(owner, tool_calls)

        # update_mood (executed) intercepted, list_available_tools
        # (not executed) passes through
        assert filtered == [
            {"name": "list_available_tools", "id": "c2"},
        ]
        assert "c1" in synthetic
        assert "c2" not in synthetic

    def test_multiple_duplicates_intercepted(self) -> None:
        """Multiple already-executed single-call tools are all
        intercepted."""
        owner = self._make_owner(
            executed_tools=["update_mood", "get_current_datetime"],
        )
        tool_calls = [
            {"name": "update_mood", "id": "c1"},
            {"name": "get_current_datetime", "id": "c2"},
            {"name": "search_news", "id": "c3"},
        ]
        filtered, synthetic = self._call(owner, tool_calls)

        assert filtered == [{"name": "search_news", "id": "c3"}]
        assert set(synthetic.keys()) == {"c1", "c2"}


class TestToolsArrayStability:
    """Regression test: self._tools identity/order preserved across
    a turn with repeated single-call tools."""

    def test_tools_array_stable_across_interception(self) -> None:
        """After interception, self._tools has same length, order,
        and name identity."""
        from airunner_services.llm.managers.mixins.tool_execution_mixin \
            import ToolExecutionMixin

        owner = MagicMock()
        owner._executed_tools = ["update_mood"]
        owner._SINGLE_CALL_TOOLS = ToolExecutionMixin._SINGLE_CALL_TOOLS
        owner._tools = [
            MagicMock(name="update_mood"),
            MagicMock(name="search_news"),
            MagicMock(name="record_knowledge"),
            MagicMock(name="search_web"),
            MagicMock(name="get_topic_brief"),
        ]
        for t, n in zip(owner._tools,
                        ["update_mood", "search_news", "record_knowledge",
                         "search_web", "get_topic_brief"]):
            t.name = n
        owner.logger = MagicMock()

        before = [(t.name, id(t)) for t in owner._tools]
        ToolExecutionMixin._intercept_single_call_duplicates(
            owner,
            [{"name": "update_mood", "id": "c1"},
             {"name": "search_news", "id": "c2"}],
        )
        after = [(t.name, id(t)) for t in owner._tools]

        assert before == after, (
            f"BUG: tool array changed! Before={before} After={after}"
        )
