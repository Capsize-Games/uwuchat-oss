"""Tests for NodePostToolInstructionsHelper turn-scoping fix.

Validates that ``add_post_tool_instructions`` only considers
``ToolMessage`` objects from the *current turn* (after the last
``HumanMessage``) — stale tool results from earlier turns must not
trigger post-tool instructions or relevance checks.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_owner() -> MagicMock:
    """Build a minimal mock workflow manager."""
    owner = MagicMock()
    owner.logger = MagicMock()
    owner._chat_model = MagicMock()
    owner._chat_model.tool_calling_mode = "react"
    return owner


def _make_helper():
    """Return (helper, owner) with a real NodePostToolInstructionsHelper."""
    from airunner_services.llm.managers.mixins import (
        node_post_tool_instructions_helper as _mod,
    )

    owner = _make_owner()
    helper = _mod.NodePostToolInstructionsHelper(owner)
    return helper, owner


# ---------------------------------------------------------------------------
# _messages_this_turn
# ---------------------------------------------------------------------------


class TestMessagesThisTurn:
    """Unit tests for _messages_this_turn slicing."""

    def test_returns_messages_after_last_human(self) -> None:
        helper, _ = _make_helper()
        HelperClass = type(helper)

        msgs = [
            HumanMessage(content="turn 1"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "a", "name": "search", "args": {}},
                ],
            ),
            ToolMessage(content="old result", tool_call_id="a"),
            AIMessage(content="turn 1 answer"),
            HumanMessage(content="turn 2"),
            AIMessage(content="turn 2 answer"),
        ]

        result = HelperClass._messages_this_turn(msgs)
        assert len(result) == 1
        assert result[0].content == "turn 2 answer"

    def test_no_human_message_returns_full_list(self) -> None:
        helper, _ = _make_helper()
        HelperClass = type(helper)

        msgs = [
            AIMessage(content="system"),
            ToolMessage(content="data", tool_call_id="x"),
        ]

        result = HelperClass._messages_this_turn(msgs)
        assert len(result) == 2

    def test_last_is_human_returns_empty(self) -> None:
        helper, _ = _make_helper()
        HelperClass = type(helper)

        msgs = [HumanMessage(content="only human")]
        result = HelperClass._messages_this_turn(msgs)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# add_post_tool_instructions — regression tests
# ---------------------------------------------------------------------------


class TestAddPostToolInstructionsTurnScoping:
    """add_post_tool_instructions ignores stale ToolMessages."""

    def test_no_instruction_when_only_stale_tool_messages(self) -> None:
        """Turn 2 has no tool call — must not inject post-tool text."""
        helper, owner = _make_helper()
        system_prompt = "You are a helpful assistant."

        trimmed = [
            HumanMessage(content="turn 1 question"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "a", "name": "search_news", "args": {}},
                ],
            ),
            ToolMessage(content="turn 1 search result", tool_call_id="a"),
            AIMessage(content="turn 1 answer"),
            HumanMessage(content="surprising follow-up comment"),
            AIMessage(content="turn 2 answer so far"),
        ]

        result = helper.add_post_tool_instructions(system_prompt, trimmed)

        assert result == system_prompt, (
            f"Expected unchanged system_prompt, got: {result}"
        )

    def test_instruction_preserved_when_tool_called_this_turn(
        self,
    ) -> None:
        """Turn with a real tool call still gets post-tool instructions."""
        helper, owner = _make_helper()
        helper._results_are_relevant = MagicMock(return_value=True)

        system_prompt = "You are a helpful assistant."

        trimmed = [
            HumanMessage(content="search for reviews"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "b", "name": "search_news", "args": {}},
                ],
            ),
            ToolMessage(content="Found great reviews.", tool_call_id="b"),
        ]

        result = helper.add_post_tool_instructions(system_prompt, trimmed)

        assert result != system_prompt
        assert "USE TOOL RESULTS" in result

    def test_last_tool_name_scoped_to_current_turn(self) -> None:
        """_last_tool_name returns None when only stale tool calls exist."""
        helper, _ = _make_helper()
        HelperClass = type(helper)

        turn_messages = [
            HumanMessage(content="turn 2 follow-up"),
            AIMessage(content="turn 2 answer"),
        ]

        result = HelperClass._last_tool_name(turn_messages)
        assert result is None, f"Expected None, got {result}"

    def test_build_instruction_counts_only_this_turn(self) -> None:
        """tool_call_count and scrape_attempts only count current turn."""
        helper, owner = _make_helper()
        owner._response_format = None
        owner._force_tool = None

        trimmed = [
            HumanMessage(content="turn 1"),
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "x", "name": "scrape_website", "args": {}},
                ],
            ),
            ToolMessage(content="data", tool_call_id="x"),
            AIMessage(content="turn 1 answer"),
            HumanMessage(content="turn 2 — no tool call"),
        ]

        turn = helper._messages_this_turn(trimmed)
        tool = helper._tool_messages(turn)

        assert len(turn) == 0
        assert len(tool) == 0


# ---------------------------------------------------------------------------
# Code-mode continuation (multi-step agentic work)
# ---------------------------------------------------------------------------


class TestCodeModeContinuation:
    """A successful code tool in code mode must NOT force-stop."""

    def _code_mode_owner(self) -> MagicMock:
        """Return an owner with a workflow manager exposing conv_id 7."""
        owner = _make_owner()
        wm = MagicMock()
        wm._conversation_id = 7
        owner._workflow_manager = wm
        return owner

    def test_code_mode_returns_continue_instruction(self) -> None:
        """In code mode, a successful execute_command yields CONTINUE
        WORKING, not TASK COMPLETED."""
        import sys
        from types import ModuleType
        from unittest.mock import patch

        import airunner_services.llm.managers.mixins.node_post_tool_instructions_helper as _mod

        stub = ModuleType("projects.uwuchat.server.code_mode_service")
        stub.code_mode_active_for_owner = lambda owner: True
        owner = self._code_mode_owner()
        helper = _mod.NodePostToolInstructionsHelper(owner)

        turn = [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "t1", "name": "execute_command", "args": {}},
                ],
            ),
            ToolMessage(content="3", tool_call_id="t1"),
        ]
        with (
            patch.dict("os.environ", {"AIRUNNER_PROJECT": "uwuchat"}),
            patch.dict(
                sys.modules,
                {"projects.uwuchat.server.code_mode_service": stub},
            ),
        ):
            result = helper._default_instruction([], turn, turn)
        assert "CONTINUE WORKING" in result
        assert "call the next tool NOW" in result

    def test_non_code_mode_still_force_stops(self) -> None:
        """Outside code mode, a task-completing tool still returns the
        TASK COMPLETED instruction."""
        import sys
        from types import ModuleType
        from unittest.mock import patch

        import airunner_services.llm.managers.mixins.node_post_tool_instructions_helper as _mod

        stub = ModuleType("projects.uwuchat.server.code_mode_service")
        stub.code_mode_active_for_owner = lambda owner: False
        owner = self._code_mode_owner()
        helper = _mod.NodePostToolInstructionsHelper(owner)

        turn = [
            AIMessage(
                content="",
                tool_calls=[
                    {"id": "t1", "name": "execute_command", "args": {}},
                ],
            ),
            ToolMessage(content="ok", tool_call_id="t1"),
        ]
        with (
            patch.dict("os.environ", {"AIRUNNER_PROJECT": "uwuchat"}),
            patch.dict(
                sys.modules,
                {"projects.uwuchat.server.code_mode_service": stub},
            ),
        ):
            result = helper._default_instruction([], turn, turn)
        assert "TASK COMPLETED" in result
