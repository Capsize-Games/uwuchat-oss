"""Tests for ForcedToolExecutionPolicy grounding-error skip."""

from __future__ import annotations

from unittest.mock import MagicMock

from langchain_core.messages import ToolMessage


def _make_policy():
    """Return (policy, owner) with a real ForcedToolExecutionPolicy."""
    from airunner_services.llm.managers.forced_tool_execution_policy import (
        ForcedToolExecutionPolicy,
    )

    owner = MagicMock()
    owner.logger = MagicMock()
    owner._force_tool = None
    owner._tool_choice = None
    owner._tools = []
    policy = ForcedToolExecutionPolicy(owner)
    return policy, owner


def test_grounding_skipped_when_tool_errored() -> None:
    """A failed search tool must not force check_grounding."""
    policy, owner = _make_policy()

    tool_calls = [
        {"id": "call_1", "name": "search_news", "args": {}},
    ]
    result_state = {
        "messages": [
            ToolMessage(
                content="ERROR: search_news is not a valid tool",
                tool_call_id="call_1",
            ),
        ],
    }

    policy.complete(tool_calls, result_state)

    # Grounding must NOT have been forced
    assert owner._force_tool is None, (
        f"Expected _force_tool=None, got {owner._force_tool}"
    )


def test_grounding_still_forced_on_success() -> None:
    """A successful search tool must still force check_grounding."""
    policy, owner = _make_policy()

    tool_calls = [
        {"id": "call_2", "name": "search_news", "args": {}},
    ]
    result_state = {
        "messages": [
            ToolMessage(
                content="Found 5 relevant results about Odyssey...",
                tool_call_id="call_2",
            ),
        ],
    }

    policy.complete(tool_calls, result_state)

    assert owner._force_tool == "check_grounding", (
        f"Expected check_grounding, got {owner._force_tool}"
    )


def test_grounding_forced_when_result_state_is_none() -> None:
    """Without result_state, existing behavior is preserved."""
    policy, owner = _make_policy()

    tool_calls = [
        {"id": "call_3", "name": "search_news", "args": {}},
    ]

    policy.complete(tool_calls, None)

    assert owner._force_tool == "check_grounding"


def test_grounding_forced_when_result_state_lacks_matching_id() -> None:
    """No matching ToolMessage found — conservative: force grounding."""
    policy, owner = _make_policy()

    tool_calls = [
        {"id": "call_4", "name": "search_news", "args": {}},
    ]
    result_state = {
        "messages": [
            ToolMessage(
                content="some other result",
                tool_call_id="other_id",
            ),
        ],
    }

    policy.complete(tool_calls, result_state)

    assert owner._force_tool == "check_grounding"


def test_error_detection_case_insensitive() -> None:
    """Both 'ERROR:' and 'Error:' prefixes are recognized."""
    policy, owner = _make_policy()

    tool_calls = [
        {"id": "call_5", "name": "scrape_website", "args": {}},
    ]
    result_state = {
        "messages": [
            ToolMessage(
                content="Error: connection refused",
                tool_call_id="call_5",
            ),
        ],
    }

    policy.complete(tool_calls, result_state)

    assert owner._force_tool is None


def test_non_search_tool_not_affected() -> None:
    """Non-grounding-forced tools are unaffected by the error check."""
    policy, owner = _make_policy()

    tool_calls = [
        {"id": "call_6", "name": "update_mood", "args": {}},
    ]
    result_state = {
        "messages": [
            ToolMessage(
                content="ERROR: something broke",
                tool_call_id="call_6",
            ),
        ],
    }

    policy.complete(tool_calls, result_state)

    # update_mood is not in _GROUNDING_FORCED_TOOLS, so nothing happens
    assert owner._force_tool is None
