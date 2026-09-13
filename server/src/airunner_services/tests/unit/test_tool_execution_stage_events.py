"""Tests for Issue 1 & 2 of the silent-tool-execution status plan.

Verifies that ``run_tool_execution_stage`` emits ``emit_tool_status``
events for each tool invocation, and that the persona rule in
``prompt_style.py`` forbids narrating search limits.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage


class TestToolExecutionStageStatusEvents:
    """Status events are emitted for each tool during cheap-stage
    tool execution."""

    def test_emits_starting_and_completed_for_each_tool(self) -> None:
        """A tool call produces one 'starting' and one 'completed'
        status event via the injected event sink."""
        from projects.uwuchat.server.tool_execution_stage import (
            run_tool_execution_stage,
        )

        chat_model = MagicMock()
        bound = MagicMock()
        chat_model.bind_tools.return_value = bound

        tc_list = [
            {
                "name": "calculator",
                "args": {"expression": "2+2"},
                "id": "tc-1",
            },
        ]
        # First call returns tool calls; second call returns DONE.
        bound.invoke.side_effect = [
            AIMessage(content="", tool_calls=tc_list),
            AIMessage(content="DONE", tool_calls=[]),
        ]

        tool_manager = MagicMock()
        tool_mock = MagicMock()
        tool_mock.name = "calculator"
        tool_mock.return_value = "4"
        tool_manager.get_tools_by_categories.return_value = [tool_mock]
        tool_manager._pii_vault = None

        event_sink = MagicMock()

        run_tool_execution_stage(
            chat_model=chat_model,
            tool_manager=tool_manager,
            prompt="what is 2+2",
            conversation_id=1,
            selected_categories=["math"],
            chatbot_id=1,
            event_sink=event_sink,
        )

        # Two calls: one starting, one completed.
        assert event_sink.emit_tool_status.call_count == 2

        call_args_list = [
            call[0][0] for call in event_sink.emit_tool_status.call_args_list
        ]

        starting = call_args_list[0]
        assert starting["tool_name"] == "calculator"
        assert starting["status"] == "starting"
        assert starting["tool_id"] == "tc-1"
        assert starting["conversation_id"] == 1

        completed = call_args_list[1]
        assert completed["tool_name"] == "calculator"
        assert completed["status"] == "completed"
        assert completed["tool_id"] == "tc-1"

    def test_emits_starting_and_completed_for_search_tool(self) -> None:
        """A search_fastsearch call emits starting/completed events
        with the query string populated from the args."""
        from projects.uwuchat.server.tool_execution_stage import (
            run_tool_execution_stage,
        )

        chat_model = MagicMock()
        bound = MagicMock()
        chat_model.bind_tools.return_value = bound

        tc_list = [
            {
                "name": "search_fastsearch",
                "args": {"queries": ["NIN band"]},
                "id": "tc-search",
            },
        ]
        # First call returns tool calls; second call returns DONE.
        bound.invoke.side_effect = [
            AIMessage(content="", tool_calls=tc_list),
            AIMessage(content="DONE", tool_calls=[]),
        ]

        tool_manager = MagicMock()
        search_tool = MagicMock()
        search_tool.name = "search_fastsearch"
        search_tool.return_value = "search results"
        tool_manager.get_tools_by_categories.return_value = [search_tool]
        tool_manager._pii_vault = None

        event_sink = MagicMock()

        run_tool_execution_stage(
            chat_model=chat_model,
            tool_manager=tool_manager,
            prompt="find NIN articles",
            conversation_id=1,
            selected_categories=["search"],
            chatbot_id=1,
            event_sink=event_sink,
        )

        assert event_sink.emit_tool_status.call_count == 2

        starting = event_sink.emit_tool_status.call_args_list[0][0][0]
        assert starting["tool_name"] == "search_fastsearch"
        assert starting["status"] == "starting"
        assert "NIN band" in starting["query"]

        completed = event_sink.emit_tool_status.call_args_list[1][0][0]
        assert completed["tool_name"] == "search_fastsearch"
        assert completed["status"] == "completed"

    def test_no_events_when_no_tools_available(self) -> None:
        """When selected_categories produces no tools, no status
        events are emitted."""
        from projects.uwuchat.server.tool_execution_stage import (
            run_tool_execution_stage,
        )

        chat_model = MagicMock()
        bound = MagicMock()
        chat_model.bind_tools.return_value = bound

        tool_manager = MagicMock()
        tool_manager.get_tools_by_categories.return_value = []

        event_sink = MagicMock()

        result = run_tool_execution_stage(
            chat_model=chat_model,
            tool_manager=tool_manager,
            prompt="hello",
            conversation_id=1,
            selected_categories=["search"],
            chatbot_id=1,
            event_sink=event_sink,
        )

        assert not result["tools_executed"]
        event_sink.emit_tool_status.assert_not_called()

    def test_no_events_when_no_categories_selected(self) -> None:
        """When selected_categories is empty/None, no events are
        emitted and the stage returns early."""
        from projects.uwuchat.server.tool_execution_stage import (
            run_tool_execution_stage,
        )

        chat_model = MagicMock()
        tool_manager = MagicMock()

        event_sink = MagicMock()

        result = run_tool_execution_stage(
            chat_model=chat_model,
            tool_manager=tool_manager,
            prompt="hello",
            conversation_id=1,
            selected_categories=None,
            chatbot_id=1,
            event_sink=event_sink,
        )

        assert not result["tools_executed"]
        event_sink.emit_tool_status.assert_not_called()

    def test_event_sink_never_raises(self) -> None:
        """If the event sink raises, the stage continues without
        crashing."""
        from projects.uwuchat.server.tool_execution_stage import (
            run_tool_execution_stage,
        )

        chat_model = MagicMock()
        bound = MagicMock()
        chat_model.bind_tools.return_value = bound

        tc_list = [
            {
                "name": "calculator",
                "args": {"expression": "1+1"},
                "id": "tc-fail",
            },
        ]
        bound.invoke.side_effect = [
            AIMessage(content="", tool_calls=tc_list),
            AIMessage(content="DONE", tool_calls=[]),
        ]

        tool_manager = MagicMock()
        tool_mock = MagicMock()
        tool_mock.name = "calculator"
        tool_mock.return_value = "2"
        tool_manager.get_tools_by_categories.return_value = [tool_mock]
        tool_manager._pii_vault = None

        event_sink = MagicMock()
        event_sink.emit_tool_status.side_effect = RuntimeError("boom")

        # Should not raise.
        result = run_tool_execution_stage(
            chat_model=chat_model,
            tool_manager=tool_manager,
            prompt="1+1",
            conversation_id=1,
            selected_categories=["math"],
            chatbot_id=1,
            event_sink=event_sink,
        )

        assert result["tools_executed"]

    def test_default_null_sink_when_none_passed(self) -> None:
        """When no event_sink is passed, the stage uses the no-op
        NullLLMWorkflowEventSink and completes without error."""
        from projects.uwuchat.server.tool_execution_stage import (
            run_tool_execution_stage,
        )

        chat_model = MagicMock()
        bound = MagicMock()
        chat_model.bind_tools.return_value = bound

        tc_list = [
            {
                "name": "calculator",
                "args": {"expression": "2+2"},
                "id": "tc-def",
            },
        ]
        bound.invoke.side_effect = [
            AIMessage(content="", tool_calls=tc_list),
            AIMessage(content="DONE", tool_calls=[]),
        ]

        tool_manager = MagicMock()
        tool_mock = MagicMock()
        tool_mock.name = "calculator"
        tool_mock.return_value = "4"
        tool_manager.get_tools_by_categories.return_value = [tool_mock]
        tool_manager._pii_vault = None

        # No event_sink passed — should default to NullLLMWorkflowEventSink
        # without crashing.
        result = run_tool_execution_stage(
            chat_model=chat_model,
            tool_manager=tool_manager,
            prompt="2+2",
            conversation_id=1,
            selected_categories=["math"],
            chatbot_id=1,
        )

        assert result["tools_executed"]

    def test_skip_msg_does_not_use_dropped_language(self) -> None:
        """The skip message for search-ceiling hits uses neutral
        language without 'dropped', 'limit', or 'capped'."""
        from projects.uwuchat.server.tool_execution_stage import (
            run_tool_execution_stage,
        )

        chat_model = MagicMock()
        bound = MagicMock()
        chat_model.bind_tools.return_value = bound

        # 7 search calls — will hit the ceiling at 5.
        tc_ids = [f"t{i}" for i in range(7)]
        tc_list = [
            {
                "name": "search_fastsearch",
                "args": {"queries": [f"q{i}"]},
                "id": tid,
            }
            for i, tid in enumerate(tc_ids)
        ]
        bound.invoke.return_value = AIMessage(content="", tool_calls=tc_list)

        tool_manager = MagicMock()
        search_tool = MagicMock()
        search_tool.name = "search_fastsearch"
        search_tool.return_value = "results"
        tool_manager.get_tools_by_categories.return_value = [search_tool]
        tool_manager._pii_vault = None

        event_sink = MagicMock()

        result = run_tool_execution_stage(
            chat_model=chat_model,
            tool_manager=tool_manager,
            prompt="search many things",
            conversation_id=1,
            selected_categories=["search"],
            chatbot_id=1,
            event_sink=event_sink,
        )

        assert result["tools_executed"]
        tool_results = result["tool_results"]

        # Find the ceiling-hit messages.
        skip_msgs = [
            tr for tr in tool_results
            if "Could not search" in tr
        ]
        assert len(skip_msgs) >= 2  # calls 6 and 7

        for msg in skip_msgs:
            assert "dropped" not in msg.lower()
            assert "limit" not in msg.lower()
            assert "capped" not in msg.lower()
            assert "Skipped" not in msg


class TestToolExecutionStageThinkingEvents:
    """Thinking events bracket the blocking model-invoke call so the
    client shows "Thinking..." instead of "Preparing..." during
    the cheap model's decision time."""

    def test_emit_thinking_brackets_entire_loop(self) -> None:
        """emit_thinking 'started' fires before the for-loop and
        'completed' fires after — one pair for the entire cheap
        stage, not per-iteration, so 'Thinking' holds across
        inter-iteration bookkeeping."""
        from projects.uwuchat.server.tool_execution_stage import (
            run_tool_execution_stage,
        )

        chat_model = MagicMock()
        bound = MagicMock()
        chat_model.bind_tools.return_value = bound

        tc_list = [
            {
                "name": "calculator",
                "args": {"expression": "2+2"},
                "id": "tc-think",
            },
        ]
        bound.invoke.side_effect = [
            AIMessage(content="", tool_calls=tc_list),
            AIMessage(content="DONE", tool_calls=[]),
        ]

        tool_manager = MagicMock()
        tool_mock = MagicMock()
        tool_mock.name = "calculator"
        tool_mock.return_value = "4"
        tool_manager.get_tools_by_categories.return_value = [tool_mock]
        tool_manager._pii_vault = None

        event_sink = MagicMock()

        run_tool_execution_stage(
            chat_model=chat_model,
            tool_manager=tool_manager,
            prompt="what is 2+2",
            conversation_id=1,
            selected_categories=["math"],
            chatbot_id=1,
            event_sink=event_sink,
        )

        thinking_calls = [
            c for c in event_sink.method_calls
            if c[0] == "emit_thinking"
        ]
        # One "started" + one "completed" for the entire loop.
        assert len(thinking_calls) == 2

        assert thinking_calls[0][1][0]["status"] == "started"
        assert thinking_calls[1][1][0]["status"] == "completed"

    def test_thinking_brackets_single_invoke(self) -> None:
        """When the model returns DONE immediately (no tool calls),
        emit_thinking is still called: started before invoke,
        completed after."""
        from projects.uwuchat.server.tool_execution_stage import (
            run_tool_execution_stage,
        )

        chat_model = MagicMock()
        bound = MagicMock()
        chat_model.bind_tools.return_value = bound

        bound.invoke.side_effect = [
            AIMessage(content="DONE", tool_calls=[]),
        ]

        tool_manager = MagicMock()
        tool_mock = MagicMock()
        tool_mock.name = "calculator"
        tool_manager.get_tools_by_categories.return_value = [tool_mock]
        tool_manager._pii_vault = None

        event_sink = MagicMock()

        run_tool_execution_stage(
            chat_model=chat_model,
            tool_manager=tool_manager,
            prompt="hello",
            conversation_id=1,
            selected_categories=["math"],
            chatbot_id=1,
            event_sink=event_sink,
        )

        # One iteration → one started + one completed.
        assert event_sink.emit_thinking.call_count == 2

        started = event_sink.emit_thinking.call_args_list[0][0][0]
        assert started["status"] == "started"
        assert started["content"] == ""

        completed = event_sink.emit_thinking.call_args_list[1][0][0]
        assert completed["status"] == "completed"
        assert completed["content"] == ""

        # bound.invoke was called exactly once.
        assert bound.invoke.call_count == 1

    def test_thinking_events_never_raise(self) -> None:
        """If emit_thinking raises, the stage continues without
        crashing."""
        from projects.uwuchat.server.tool_execution_stage import (
            run_tool_execution_stage,
        )

        chat_model = MagicMock()
        bound = MagicMock()
        chat_model.bind_tools.return_value = bound

        bound.invoke.side_effect = [
            AIMessage(content="DONE", tool_calls=[]),
        ]

        tool_manager = MagicMock()
        tool_mock = MagicMock()
        tool_mock.name = "calculator"
        tool_manager.get_tools_by_categories.return_value = [tool_mock]
        tool_manager._pii_vault = None

        event_sink = MagicMock()
        event_sink.emit_thinking.side_effect = RuntimeError("boom")

        # Should not raise.
        result = run_tool_execution_stage(
            chat_model=chat_model,
            tool_manager=tool_manager,
            prompt="hello",
            conversation_id=1,
            selected_categories=["math"],
            chatbot_id=1,
            event_sink=event_sink,
        )

        assert not result["tools_executed"]

    def test_thinking_events_preserve_round1_tool_status(self) -> None:
        """The round-1 emit_tool_status calls are still emitted
        alongside the new emit_thinking calls."""
        from projects.uwuchat.server.tool_execution_stage import (
            run_tool_execution_stage,
        )

        chat_model = MagicMock()
        bound = MagicMock()
        chat_model.bind_tools.return_value = bound

        tc_list = [
            {
                "name": "calculator",
                "args": {"expression": "2+2"},
                "id": "tc-preserve",
            },
        ]
        bound.invoke.side_effect = [
            AIMessage(content="", tool_calls=tc_list),
            AIMessage(content="DONE", tool_calls=[]),
        ]

        tool_manager = MagicMock()
        tool_mock = MagicMock()
        tool_mock.name = "calculator"
        tool_mock.return_value = "4"
        tool_manager.get_tools_by_categories.return_value = [tool_mock]
        tool_manager._pii_vault = None

        event_sink = MagicMock()

        run_tool_execution_stage(
            chat_model=chat_model,
            tool_manager=tool_manager,
            prompt="2+2",
            conversation_id=1,
            selected_categories=["math"],
            chatbot_id=1,
            event_sink=event_sink,
        )

        # Round-1 emit_tool_status: 2 calls (starting + completed).
        assert event_sink.emit_tool_status.call_count == 2
        # Round-2 emit_thinking: 2 calls (loop-wide started/completed).
        assert event_sink.emit_thinking.call_count == 2


class TestTruncateQueriesMessage:
    """The _truncate_queries note uses neutral language."""

    def test_truncation_note_is_neutral(self) -> None:
        """The synthetic query appended when queries exceed the cap
        does not contain 'dropped', 'limit', or 'capped' language
        that the model would narrate back to the user."""
        from extensions.fastsearch.server.tools import _truncate_queries

        queries = [f"query-{i}" for i in range(8)]
        result = _truncate_queries(queries, "search_fastsearch")

        # Should have _MAX_QUERIES_PER_CALL + 1 entries (the extra is
        # the synthetic note).
        from extensions.fastsearch.server.tools import (
            _MAX_QUERIES_PER_CALL,
        )
        assert len(result) == _MAX_QUERIES_PER_CALL + 1

        note = result[-1]
        assert "dropped" not in note.lower()
        assert "limit" not in note.lower()
        assert "capped" not in note.lower()
        assert "max" not in note.lower()
        assert "re-query" not in note.lower()
        # The new message says "searched the first N queries out of M"
        assert "searched the first" in note


class TestPromptStyleAntiNarrationRule:
    """The persona rule now forbids narrating search limits."""

    def test_anti_narration_rule_in_generated_prompt(self) -> None:
        """The generated RP style block includes the rule forbidding
        narration of internal mechanics and search limits."""
        from projects.uwuchat.server.prompt_style import uwuchat_rp_style

        prompt = uwuchat_rp_style("TestBot")

        assert "NEVER narrate internal mechanics" in prompt
        assert "system capped me" in prompt
        assert "search limit" in prompt
        assert "dropped queries" in prompt

    def test_old_tool_name_rule_still_present(self) -> None:
        """The existing rule about not mentioning tool names is
        preserved alongside the new rule."""
        from projects.uwuchat.server.prompt_style import uwuchat_rp_style

        prompt = uwuchat_rp_style("TestBot")

        assert "NEVER mention tool names" in prompt
        assert "search_fastsearch" in prompt
        assert "according to my search" in prompt
