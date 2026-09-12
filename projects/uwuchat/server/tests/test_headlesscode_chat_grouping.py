"""Tests for the Python port of headlesscode's chat-thread grouping.

Ports the fixture cases from headlesscode's own
``src/dashboard/__tests__/chat-thread.test.ts`` so the Python
``group_events_into_chat`` is verified against the same behaviors the
dashboard's TypeScript implementation is.
"""

from __future__ import annotations

from projects.uwuchat.server.headlesscode_chat_grouping import (
    chat_block_kinds,
    group_events_into_chat,
)


def _event(etype: str, **extra) -> dict:
    """Build one feed event, mirroring the TS test helper."""
    return {
        "ts": "2026-08-01T00:00:00.000Z", "sessionId": "session-1",
        "type": etype, **extra,
    }


def _turns(group: dict) -> list[list[dict]]:
    """Extract each turn block's events, mirroring the TS helper."""
    return [
        block["events"]
        for block in group["blocks"]
        if block["kind"] == "turn"
    ]


def _systems(group: dict) -> list[dict]:
    """Extract each system marker's event, mirroring the TS helper."""
    return [
        block["event"]
        for block in group["blocks"]
        if block["kind"] == "system"
    ]


def test_normal_turn_groups_into_turn() -> None:
    """session_start + checkpoint are system; the rest is one turn."""
    events = [
        _event("session_start", task="fix the bug"),
        _event("checkpoint_saved", iteration=0),
        _event("iteration_start", iteration=1),
        _event("llm_response", iteration=1, hadToolCalls=True,
               textPreview="I'll look."),
        _event("tool_call", iteration=1, tool="read_file",
               args="src/a.ts"),
        _event("tool_result", iteration=1, tool="read_file",
               isError=False, result="contents"),
    ]

    group = group_events_into_chat(events)
    assert group["task"] == "fix the bug"
    assert [b["kind"] for b in group["blocks"][:2]] == [
        "system", "system",
    ]
    turn = group["blocks"][2]
    assert turn["kind"] == "turn"
    assert turn["iteration"] == 1
    assert [e["type"] for e in turn["events"]] == [
        "llm_response", "tool_call", "tool_result",
    ]


def test_multiple_tool_calls_stay_in_one_turn() -> None:
    """Two call/result pairs belong to the SAME turn."""
    events = [
        _event("iteration_start", iteration=2),
        _event("llm_response", iteration=2, hadToolCalls=True,
               textPreview=""),
        _event("tool_call", iteration=2, tool="list_files", args="."),
        _event("tool_result", iteration=2, tool="list_files",
               isError=False, result="a\nb"),
        _event("tool_call", iteration=2, tool="read_file",
               args="src/b.ts"),
        _event("tool_result", iteration=2, tool="read_file",
               isError=False, result="code"),
    ]

    turns = _turns(group_events_into_chat(events))
    assert len(turns) == 1
    assert [e["type"] for e in turns[0]] == [
        "llm_response", "tool_call", "tool_result",
        "tool_call", "tool_result",
    ]
    assert turns[0][1]["tool"] == "list_files"
    assert turns[0][3]["tool"] == "read_file"


def test_error_tool_result_stays_with_its_call() -> None:
    """An error result is attached to its call, not orphaned."""
    events = [
        _event("iteration_start", iteration=3),
        _event("llm_response", iteration=3, hadToolCalls=True,
               textPreview="running"),
        _event("tool_call", iteration=3, tool="execute_command",
               args="rm -rf /"),
        _event("tool_result", iteration=3, tool="execute_command",
               isError=True, result="permission denied"),
    ]

    turns = _turns(group_events_into_chat(events))
    assert len(turns) == 1
    assert turns[0][2]["isError"] is True
    assert turns[0][2]["tool"] == "execute_command"


def test_decision_blocked_answered_pair() -> None:
    """decision_blocked starts its own turn; the answer is its content."""
    events = [
        _event("iteration_start", iteration=4),
        _event("llm_response", iteration=4, hadToolCalls=True,
               textPreview="a question"),
        _event("tool_call", iteration=4, tool="ask_followup_question",
               args="proceed?"),
        _event("tool_result", iteration=4,
               tool="ask_followup_question", isError=False,
               result="waiting"),
        _event("decision_blocked", question="proceed?"),
        _event("decision_answered", answer="yes", timedOut=False),
    ]

    group = group_events_into_chat(events)
    assert len(_turns(group)) == 2
    assert [e["type"] for e in _turns(group)[1]] == [
        "decision_answered",
    ]
    starts = [b for b in group["blocks"]
              if b["kind"] == "turn"
              and b["turnStart"]["type"] == "decision_blocked"]
    assert starts[0]["turnStart"]["question"] == "proceed?"


def test_pause_resume_pair_are_system_markers() -> None:
    """paused/resumed close the turn and render as system markers."""
    events = [
        _event("iteration_start", iteration=5),
        _event("llm_response", iteration=5, hadToolCalls=False,
               textPreview="almost done"),
        _event("paused", reason="human asked"),
        _event("resumed", reason="ok go"),
    ]

    group = group_events_into_chat(events)
    assert [e["type"] for e in _systems(group)] == ["paused", "resumed"]
    assert len(_turns(group)) == 1


def test_stream_chunks_stay_in_current_turn() -> None:
    """llm_stream_chunk events must NOT fragment the turn."""
    events = [
        _event("iteration_start", iteration=2),
        _event("llm_stream_chunk", iteration=2, kind="reasoning",
               chunk="think"),
        _event("llm_stream_chunk", iteration=2, kind="text",
               chunk="Hello"),
        _event("llm_response", iteration=2, hadToolCalls=False,
               textPreview="Hello", outputTokens=5),
        _event("tool_call", iteration=2, tool="attempt_completion",
               args="done"),
        _event("tool_result", iteration=2, tool="attempt_completion",
               isError=False, result="ok"),
        _event("session_end", status="success", iterations=2),
    ]

    group = group_events_into_chat(events)
    turns = _turns(group)
    assert len(turns) == 1
    assert [e["type"] for e in turns[0]] == [
        "llm_stream_chunk", "llm_stream_chunk", "llm_response",
        "tool_call", "tool_result",
    ]
    assert turns[0][0]["kind"] == "reasoning"
    assert [e["type"] for e in _systems(group)] == ["session_end"]


def test_lone_stream_chunk_is_system_marker() -> None:
    """A feed that starts mid-stream degrades to a system marker."""
    group = group_events_into_chat([
        _event("llm_stream_chunk", iteration=1, kind="text",
               chunk="orphan"),
    ])
    assert len(_systems(group)) == 1
    assert _systems(group)[0]["type"] == "llm_stream_chunk"
    assert len(_turns(group)) == 0


def test_session_end_closes_turn_and_is_system_marker() -> None:
    """session_end closes the open turn and renders as a marker."""
    events = [
        _event("iteration_start", iteration=6),
        _event("llm_response", iteration=6, hadToolCalls=False,
               textPreview="done"),
        _event("session_end", status="success", iterations=6,
               costUsd=0.01, inputTokens=100, outputTokens=50),
    ]

    group = group_events_into_chat(events)
    assert len(_turns(group)) == 1
    assert [e["type"] for e in _systems(group)] == ["session_end"]


def test_empty_feed_and_no_task() -> None:
    """An empty feed yields no blocks; a task-less session_start has
    no ``task`` key."""
    assert group_events_into_chat([])["blocks"] == []
    no_task = group_events_into_chat([_event("session_start")])
    assert "task" not in no_task
    assert [b["kind"] for b in no_task["blocks"]] == ["system"]


def test_orphaned_tool_result_is_system_marker() -> None:
    """A result with no preceding call in the turn is a marker."""
    events = [
        _event("tool_result", iteration=1, tool="read_file",
               isError=False, result="lonely"),
        _event("iteration_start", iteration=1),
        _event("tool_call", iteration=1, tool="read_file", args="x.ts"),
        _event("tool_result", iteration=1, tool="read_file",
               isError=False, result="ok"),
    ]

    group = group_events_into_chat(events)
    systems = _systems(group)
    assert len(systems) == 1
    assert systems[0]["type"] == "tool_result"
    assert len(_turns(group)) == 1


def test_chat_block_kinds_parallel_to_events() -> None:
    """chat_block_kinds returns one kind per event, in feed order."""
    events = [
        _event("iteration_start", iteration=1),
        _event("llm_response", iteration=1, textPreview="hi"),
        _event("tool_call", iteration=1, tool="read_file", args="a"),
        _event("tool_result", iteration=1, tool="read_file",
               isError=False, result="ok"),
        _event("paused", reason="asked"),
    ]

    kinds = chat_block_kinds(events)
    assert kinds == ["turn", "turn", "turn", "turn", "system"]


