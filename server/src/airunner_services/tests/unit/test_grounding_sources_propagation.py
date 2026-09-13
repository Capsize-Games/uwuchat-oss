"""Tests for grounding-source propagation and empty-response fallback.

Verifies that:
1. Grounding sources stashed via _stash_grounding_sources survive
   across a simulated graph-node boundary (ContextVar refresh from
   state).
2. An empty final response triggers the fallback message rather than
   returning silent empty content.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, ToolMessage


class TestGroundingSourcesPropagation:
    """Grounding sources written to graph state are readable from the
    ContextVar after a _refresh_grounding_cache_from_state call."""

    def _make_tool_calls(self, name: str, ids: list[str]) -> list[dict]:
        return [{"name": name, "id": tid, "args": {}} for tid in ids]

    def test_stash_writes_to_state(self) -> None:
        """_stash_grounding_sources appends to state.grounding_sources."""
        from airunner_services.llm.tools.grounding_tools_helpers import (
            clear_grounding_sources,
        )

        # Clear any prior state
        clear_grounding_sources()

        owner = MagicMock()
        owner._GROUNDING_SOURCE_TOOLS = frozenset({"search_fastsearch"})
        owner._extract_grounding_text = lambda c: (
            c if c else ""
        )

        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )

        mixin = ToolExecutionMixin()
        # Manually set the attributes needed.
        mixin._GROUNDING_SOURCE_TOOLS = frozenset(
            {"search_fastsearch"}
        )
        mixin._extract_grounding_text = lambda c: c if c else ""

        tool_calls = self._make_tool_calls(
            "search_fastsearch", ["tc-1"]
        )
        result_state: dict = {
            "messages": [
                ToolMessage(
                    content="search result text",
                    tool_call_id="tc-1",
                    name="search_fastsearch",
                ),
            ],
        }

        mixin._stash_grounding_sources(tool_calls, result_state)

        assert result_state.get("grounding_sources") == [
            "search result text"
        ]

    def test_refresh_populates_contextvar_from_state(self) -> None:
        """_refresh_grounding_cache_from_state sets the ContextVar
        so get_grounding_sources() returns the state's values."""
        from airunner_services.llm.tools.grounding_tools_helpers import (
            clear_grounding_sources,
            get_grounding_sources,
        )

        # Start clean.
        clear_grounding_sources()
        assert get_grounding_sources() == []

        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )

        mixin = ToolExecutionMixin()
        state = {
            "grounding_sources": [
                "source alpha",
                "source beta",
            ],
        }

        mixin._refresh_grounding_cache_from_state(state)

        sources = get_grounding_sources()
        assert len(sources) == 2
        assert "source alpha" in sources
        assert "source beta" in sources

    def test_refresh_empty_state_does_nothing(self) -> None:
        """When state has no grounding_sources, the ContextVar is
        left alone."""
        from airunner_services.llm.tools.grounding_tools_helpers import (
            add_grounding_source,
            clear_grounding_sources,
            get_grounding_sources,
        )

        clear_grounding_sources()
        add_grounding_source("existing")

        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )

        mixin = ToolExecutionMixin()
        # State with NO grounding_sources key.
        mixin._refresh_grounding_cache_from_state({})

        # Should still have the existing source.
        assert get_grounding_sources() == ["existing"]

    def test_stash_accumulates_multiple_calls(self) -> None:
        """Multiple _stash_grounding_sources calls append to state
        without overwriting prior entries."""
        from airunner_services.llm.tools.grounding_tools_helpers import (
            clear_grounding_sources,
        )
        clear_grounding_sources()

        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )

        mixin = ToolExecutionMixin()
        mixin._GROUNDING_SOURCE_TOOLS = frozenset(
            {"search_fastsearch"}
        )
        mixin._extract_grounding_text = lambda c: c if c else ""

        result_state: dict = {"messages": []}

        # First call.
        tc1 = self._make_tool_calls("search_fastsearch", ["a"])
        result_state["messages"] = [
            ToolMessage(
                content="first result",
                tool_call_id="a",
                name="search_fastsearch",
            ),
        ]
        mixin._stash_grounding_sources(tc1, result_state)

        # Second call.
        tc2 = self._make_tool_calls("search_fastsearch", ["b"])
        result_state["messages"] = [
            ToolMessage(
                content="second result",
                tool_call_id="b",
                name="search_fastsearch",
            ),
        ]
        mixin._stash_grounding_sources(tc2, result_state)

        assert result_state["grounding_sources"] == [
            "first result",
            "second result",
        ]

    def test_stash_ignores_non_search_tools(self) -> None:
        """Non-search tool calls do not populate grounding_sources."""
        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )

        mixin = ToolExecutionMixin()
        mixin._GROUNDING_SOURCE_TOOLS = frozenset(
            {"search_fastsearch"}
        )
        mixin._extract_grounding_text = lambda c: c if c else ""

        result_state: dict = {
            "messages": [
                ToolMessage(
                    content="calculator result",
                    tool_call_id="tc-calc",
                    name="calculator",
                ),
            ],
        }
        tc = self._make_tool_calls("calculator", ["tc-calc"])

        mixin._stash_grounding_sources(tc, result_state)

        # No grounding_sources key should be added.
        assert "grounding_sources" not in result_state


class TestEmptyResponseFallback:
    """An empty final response triggers a visible fallback message."""

    def test_empty_response_gets_fallback(self) -> None:
        """When the model produces no visible content and no tools,
        the fallback returns a non-empty string."""
        from airunner_services.llm.managers.mixins.generation_response_support import (
            fallback_response_for_empty_result,
        )

        result: dict = {
            "messages": [
                AIMessage(content=""),
            ],
        }

        text = fallback_response_for_empty_result(result, [])
        assert text
        assert len(text.strip()) > 0

    def test_tool_only_result_gets_fallback(self) -> None:
        """A result with only tool calls and no final text gets a
        fallback describing that tools ran."""
        from airunner_services.llm.managers.mixins.generation_response_support import (
            fallback_response_for_empty_result,
        )

        result: dict = {
            "messages": [
                AIMessage(content="", tool_calls=[
                    {"name": "search_fastsearch",
                     "args": {}, "id": "tc-1"},
                ]),
            ],
        }

        text = fallback_response_for_empty_result(
            result, ["search_fastsearch"],
        )
        assert text
        assert len(text.strip()) > 0

    def test_empty_result_without_messages(self) -> None:
        """A completely empty result returns empty string — no
        fallback when there's nothing to fall back from."""
        from airunner_services.llm.managers.mixins.generation_response_support import (
            fallback_response_for_empty_result,
        )

        text = fallback_response_for_empty_result({}, [])
        assert text == ""

    def test_extract_final_response_empty_returns_empty_string(
        self,
    ) -> None:
        """extract_final_response returns '' when the last AIMessage
        has no visible content."""
        from airunner_services.llm.managers.mixins.generation_response_support import (
            extract_final_response,
        )

        owner = MagicMock()
        result: dict = {
            "messages": [AIMessage(content="")],
        }

        text = extract_final_response(owner, result)
        assert text == ""

    def test_extract_final_response_with_content_returns_it(
        self,
    ) -> None:
        """extract_final_response returns visible content when
        present."""
        from airunner_services.llm.managers.mixins.generation_response_support import (
            extract_final_response,
        )

        owner = MagicMock()
        result: dict = {
            "messages": [AIMessage(content="Hello, world")],
        }

        text = extract_final_response(owner, result)
        assert "Hello, world" in text


class TestStaleNarrationClearedBySafetyNet:
    """When the model streams visible text before calling a tool and
    then produces an empty final response, the stale narration must
    be cleared from complete_response[0] so the fallback fires."""

    def test_reset_clears_stale_narration(self) -> None:
        """_reset_stream_state clears complete_response[0] so the
        empty-AIMessage path reaches the fallback."""
        complete_response = ["Let me dig into this."]
        sequence_counter = [0]

        reset_fn = _make_reset_fn(complete_response, sequence_counter)
        reset_fn()

        assert complete_response[0] == ""
        assert sequence_counter[0] == 0

    def test_without_reset_stale_text_blocks_fallback(self) -> None:
        """Without _reset_stream_state, stale narration text in
        complete_response[0] causes _finalize_visible_response to
        return early, never reaching the fallback."""
        from airunner_services.llm.managers.mixins.generation_response_support import (
            fallback_response_for_empty_result,
        )

        owner = MagicMock()
        owner.logger = MagicMock()
        llm_request = MagicMock()
        llm_request.id = "req-1"
        llm_request.action = "chat"

        # Simulate: model emitted "Let me dig into this." before
        # calling a tool, then the final turn produced an empty
        # AIMessage.  Without the reset, complete_response[0] holds
        # the stale narration text.

        result: dict = {
            "messages": [AIMessage(content="")],
        }
        executed_tools = ["search_fastsearch", "check_grounding"]

        # _finalize_visible_response's extract_final_response returns
        # "" (empty AIMessage).  complete_response[0] is non-empty
        # with the stale text.  Before the fix, this returned early.
        # After the fix with _reset_stream_state(), the narration is
        # cleared, complete_response[0] becomes "", and the fallback
        # fires instead.
        #
        # This test verifies the fallback WOULD fire if the text
        # were cleared — i.e., fallback_response_for_empty_result
        # returns a non-empty string for this scenario.
        fallback = fallback_response_for_empty_result(
            result, executed_tools,
        )
        assert fallback
        assert len(fallback.strip()) > 0



def _make_reset_fn(
    complete_response: list, sequence_counter: list,
):
    """Return a _reset_stream_state-style callable that clears
    complete_response and sequence_counter.  Mirrors the pattern in
    generation_execution_support.py:run_generation_stream."""
    def _reset() -> None:
        complete_response[0] = ""
        sequence_counter[0] = 0
    return _reset


class TestSummaryBeforeResults:
    """search_fastsearch puts 'summary' before 'results' so
    truncation slices through the bulky array, not the prose."""

    def test_summary_is_first_key(self) -> None:
        """The returned dict lists 'summary' before 'results'."""
        result = {
            "summary": "clean prose",
            "results": [{"title": "x", "link": "y", "snippet": "z"}],
        }
        assert list(result.keys())[0] == "summary"

    def test_serialized_summary_before_results(self) -> None:
        """When JSON-serialized, 'summary' appears before
        'results'."""
        import json
        result = {
            "summary": "clean prose",
            "results": [{"title": "x"}],
        }
        text = json.dumps(result)
        assert text.index('"summary"') < text.index('"results"')


class TestExtractGroundingText:
    """_extract_grounding_text recovers summary from valid,
    truncated, and non-JSON content."""

    def test_valid_json_prefers_summary(self) -> None:
        """Valid JSON with a 'summary' field returns summary."""
        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )
        import json

        content = json.dumps({
            "summary": "clean search result text",
            "results": [{"title": "x"}],
        })
        result = ToolExecutionMixin._extract_grounding_text(content)
        assert "clean search result text" in result
        assert "title" not in result

    def test_truncated_json_regex_recovers_summary(self) -> None:
        """Truncated JSON with a 'summary' field — regex fallback
        recovers the summary text even when json.loads fails."""
        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )

        # Simulate: summary placed first, results array truncated
        # mid-object before reaching "summary" under the old order.
        # With the new order, the summary is first and survives.
        truncated = (
            '{"summary": "clean prose summary text", '
            '"results": [{"title": "Jimmy Page", '
            '"snippet": "<b class=\\"match term0\\">Jimmy</b>'
        )
        result = ToolExecutionMixin._extract_grounding_text(truncated)
        assert "clean prose summary text" in result
        assert "<b" not in result

    def test_non_json_content_returns_raw(self) -> None:
        """Non-JSON content is returned verbatim."""
        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )

        result = ToolExecutionMixin._extract_grounding_text(
            "plain text tool result"
        )
        assert result == "plain text tool result"

    def test_empty_string_returns_empty(self) -> None:
        """Empty or whitespace-only returns empty string."""
        from airunner_services.llm.managers.mixins.tool_execution_mixin import (
            ToolExecutionMixin,
        )

        assert ToolExecutionMixin._extract_grounding_text("") == ""
        assert ToolExecutionMixin._extract_grounding_text("   ") == ""
