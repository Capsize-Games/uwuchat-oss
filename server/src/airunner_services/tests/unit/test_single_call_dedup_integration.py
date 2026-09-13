"""Integration test for single-call dedup in _execute_tools_with_status.

Calls the REAL _execute_tools_with_status with a mocked ToolNode to
verify that duplicate single-call tools never reach tool execution.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

# Must run the runtime compat shim before ToolNode is imported.
from airunner_services.llm.managers.mixins.tool_execution_mixin import (
    ToolExecutionMixin,
)
ToolExecutionMixin._ensure_runtime_compat()


class _FakeToolNode:
    """Fake ToolNode that records received tool_calls and returns
    synthetic ToolMessages without needing the LangGraph runtime."""

    def __init__(self, tools):
        self.tools = tools
        self.received_calls: list[dict] = []

    def invoke(self, state):
        last_msg = state["messages"][-1]
        tcs = getattr(last_msg, "tool_calls", []) or []
        self.received_calls.extend(tcs)
        msgs = []
        for tc in tcs:
            msgs.append(
                ToolMessage(
                    content=f"Result for {tc['name']}",
                    tool_call_id=tc["id"],
                )
            )
        return {"messages": msgs}


class TestSingleCallDedupIntegration:
    """Integration tests calling real _execute_tools_with_status."""

    @staticmethod
    def _make_owner(executed_tools=None, real_tool_func=None):
        owner = MagicMock()
        owner.logger = MagicMock()
        owner._executed_tools = list(executed_tools or [])
        owner._SINGLE_CALL_TOOLS = (
            ToolExecutionMixin._SINGLE_CALL_TOOLS
        )
        if real_tool_func is not None:
            owner._tools = [real_tool_func]
        else:
            owner._tools = []
        # Wire the real helper
        owner._intercept_single_call_duplicates = (
            lambda tcs: ToolExecutionMixin
            ._intercept_single_call_duplicates(owner, tcs)
        )
        # Silently accept all other hook calls
        for attr in (
            "_prebind_for_pending_category_switch",
            "_sanitize_tool_functions",
        ):
            setattr(owner, attr, lambda *a, **kw: None)
        owner._emit_starting_status = lambda tcs: None
        owner._emit_completed_status = lambda rs, tcs: None
        owner._stash_grounding_sources = lambda tcs, rs: None
        owner._maybe_restore_mood_state = lambda rs: None
        owner._record_tool_usage = lambda tcs: None
        owner._handle_category_switch = lambda tcs, rs: None
        owner._ensure_tools_loaded = lambda tcs, s: None
        pol = MagicMock()
        pol.prepare = lambda s, tcs: (s, tcs, None)
        pol.complete = lambda tcs, rs: None
        owner._get_forced_tool_policy = MagicMock(return_value=pol)
        return owner

    def test_duplicates_not_received_by_tool_node(self) -> None:
        """Duplicate single-call tools are NOT passed to ToolNode."""
        def _search_news(query: str) -> str:
            """Search for news articles."""
            return f"results for {query}"
        _search_news.__name__ = "search_news"

        owner = self._make_owner(
            executed_tools=["update_mood"],
            real_tool_func=_search_news,
        )

        aim = AIMessage(
            content="",
            tool_calls=[
                {"name": "search_news", "id": "c1",
                 "args": {"query": "test"}},
                {"name": "update_mood", "id": "c2",
                 "args": {"mood": "happy"}},
            ],
        )
        state = {"messages": [HumanMessage(content="hi"), aim]}

        with patch(
            "langgraph.prebuilt.ToolNode",
            return_value=_FakeToolNode(owner._tools),
        ) as mock_tool_node_cls:
            result = ToolExecutionMixin._execute_tools_with_status(
                owner, state,
            )

        # Verify: ToolNode only received non-duplicate calls
        fake = mock_tool_node_cls.return_value
        received_names = {tc["name"] for tc in fake.received_calls}
        assert "search_news" in received_names
        assert "update_mood" not in received_names, (
            "BUG: duplicate update_mood was passed to ToolNode"
        )

        # Verify: one ToolMessage per call_id, no duplicates
        msgs = result.get("messages", [])
        tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
        ids = [m.tool_call_id for m in tool_msgs]
        assert len(ids) == 2, f"Expected 2 ToolMessages, got {len(ids)}"
        assert len(ids) == len(set(ids)), f"Duplicate call_ids: {ids}"
        # search_news result from ToolNode
        assert any(m.tool_call_id == "c1" for m in tool_msgs)
        # update_mood synthetic from interception
        synth = [m for m in tool_msgs if m.tool_call_id == "c2"]
        assert len(synth) == 1
        assert "already executed" in str(synth[0].content)

        # Verify: self._tools unchanged
        assert owner._tools == [_search_news]

    def test_all_duplicates_tool_node_not_called(self) -> None:
        """When ALL tool calls are duplicates, ToolNode.invoke is never
        called (ToolNode may or may not be constructed depending on the
        early-return guard)."""
        owner = self._make_owner(
            executed_tools=["update_mood", "get_current_datetime"],
            real_tool_func=None,
        )

        aim = AIMessage(
            content="",
            tool_calls=[
                {"name": "update_mood", "id": "c1",
                 "args": {"mood": "happy"}},
                {"name": "get_current_datetime", "id": "c2", "args": {}},
            ],
        )
        state = {"messages": [HumanMessage(content="hi"), aim]}

        with patch(
            "langgraph.prebuilt.ToolNode",
        ) as mock_tool_node_cls:
            result = ToolExecutionMixin._execute_tools_with_status(
                owner, state,
            )

        # ToolNode should never be constructed (active_calls was empty)
        mock_tool_node_cls.assert_not_called()

        # All results are synthetic
        msgs = result.get("messages", [])
        tool_msgs = [m for m in msgs if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 2
        assert all(
            "already executed" in str(m.content) for m in tool_msgs
        )

        # self._tools unchanged
        assert owner._tools == []
