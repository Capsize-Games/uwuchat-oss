"""Tests for the headlesscode per-session event-poll task (Phase 4).

Follows the launch-task test conventions
(test_headlesscode_launch_task.py): all DB and Redis interactions are
mocked — no real tenant schema, Redis, or dashboard needed. Shared
fakes live in ``fakes_headlesscode``; the Beat trigger and the credit
settlement helpers are covered in test_headlesscode_poll_trigger.py.
"""

from __future__ import annotations

from projects.uwuchat.server.tests.fakes_headlesscode import (
    FakeSession,
    patch_outbox,
    project_row,
    run_poll_task,
    session_row,
)

# One iteration feed event + its poll response, shared by the
# non-terminal poll tests.
_ITERATION = {
    "ts": "2026-08-01T00:00:00Z", "sessionId": "hc-abc123",
    "type": "iteration_start", "iteration": 1,
}
_FEED = {
    "sessionId": "hc-abc123",
    "events": [_ITERATION],
    "nextOffset": 240,
}


def test_poll_persists_events_and_advances_offset(
    monkeypatch,
) -> None:
    """New events persist with their grouping kind; offset advances."""
    fake = FakeSession(
        sessions=[session_row(event_offset=0)],
        projects=[project_row()],
        stored_events=[],
    )

    result = run_poll_task(monkeypatch, fake, [_FEED])

    assert result == {"status": "ok", "events": 1}
    assert fake.sessions[1].event_offset == 240
    assert len(fake.added) == 1
    added = fake.added[0]
    assert added.session_id == 1
    assert added.raw_event["type"] == "iteration_start"
    assert added.chat_block_kind == "turn"


def test_poll_forwards_new_events_to_outbox(monkeypatch) -> None:
    """Each persisted event reaches the outbox with its owner scoped."""
    fake = FakeSession(
        sessions=[session_row(event_offset=0)],
        projects=[project_row()],
    )

    captured = patch_outbox(monkeypatch)
    result = run_poll_task(
        monkeypatch, fake, [_FEED], outbox=captured,
    )

    assert result == {"status": "ok", "events": 1}
    assert len(captured) == 1
    payload = captured[0]
    assert payload["account_id"] == 42
    assert payload["session_id"] == 1
    assert payload["headlesscode_session_id"] == "hc-abc123"
    assert payload["chat_block_kind"] == "turn"
    assert payload["event"] is _ITERATION


def test_poll_survives_post_commit_detach(monkeypatch) -> None:
    """No ORM attribute is read after commit (expire-on-commit)."""
    from projects.uwuchat.server.tests.fakes_headlesscode import (
        ExpiringFakeSession,
    )

    fake = ExpiringFakeSession(
        sessions=[session_row(event_offset=0)],
        projects=[project_row()],
    )
    captured = patch_outbox(monkeypatch)
    result = run_poll_task(
        monkeypatch, fake, [_FEED], outbox=captured,
    )

    assert result == {"status": "ok", "events": 1}
    assert len(captured) == 1
    assert captured[0]["account_id"] == 42


def test_poll_tool_result_attaches_across_poll_batches(
    monkeypatch,
) -> None:
    """A tool_result in the new batch attaches to a stored tool_call."""
    stored = [
        {
            "ts": "2026-08-01T00:00:00Z", "sessionId": "hc-abc123",
            "type": "iteration_start", "iteration": 1,
        },
        {
            "ts": "2026-08-01T00:00:00Z", "sessionId": "hc-abc123",
            "type": "tool_call", "iteration": 1, "tool": "read_file",
        },
    ]
    fake = FakeSession(
        sessions=[session_row(event_offset=100)],
        projects=[project_row()],
        stored_events=stored,
    )
    tool_result = {
        "ts": "2026-08-01T00:00:01Z", "sessionId": "hc-abc123",
        "type": "tool_result", "iteration": 1, "tool": "read_file",
        "isError": False, "result": "ok",
    }
    response = {"sessionId": "hc-abc123", "events": [tool_result],
                "nextOffset": 200}

    result = run_poll_task(monkeypatch, fake, [response])

    assert result == {"status": "ok", "events": 1}
    assert len(fake.added) == 1
    assert fake.added[0].chat_block_kind == "turn"
    assert fake.sessions[1].event_offset == 200


def test_poll_terminal_session_end_settles_cost(monkeypatch) -> None:
    """session_end completes the session and debits the real cost."""
    from decimal import Decimal

    from projects.uwuchat.server.tests.fakes_headlesscode import (
        patch_finalize,
    )

    fake = FakeSession(
        sessions=[session_row(event_offset=0)],
        projects=[project_row()],
    )
    session_end = {
        "ts": "2026-08-01T00:00:02Z", "sessionId": "hc-abc123",
        "type": "session_end", "status": "success", "iterations": 2,
        "costUsd": 0.42,
    }
    response = {"sessionId": "hc-abc123", "events": [session_end],
                "nextOffset": 300}

    captured = patch_outbox(monkeypatch)
    finalize_calls = patch_finalize(monkeypatch)
    result = run_poll_task(
        monkeypatch, fake, [response], outbox=captured,
    )

    assert result == {"status": "ok", "events": 1}
    assert fake.sessions[1].status == "completed"
    assert finalize_calls == [
        ((42, "hc-abc123", Decimal("0.42")), {}),
    ]
    # One event payload + one status-change payload.
    assert len(captured) == 2
    assert captured[0]["event"] is session_end
    assert captured[0]["status"] == "completed"
    assert captured[1]["event"] is None
    assert captured[1]["status"] == "completed"


def test_poll_session_end_error_marks_failed(monkeypatch) -> None:
    """A session_end with error status marks the session failed."""
    fake = FakeSession(
        sessions=[session_row()],
        projects=[project_row()],
    )
    session_end = {
        "ts": "2026-08-01T00:00:02Z", "sessionId": "hc-abc123",
        "type": "session_end", "status": "error", "iterations": 1,
        "costUsd": 0.05,
    }
    response = {"sessionId": "hc-abc123", "events": [session_end],
                "nextOffset": 300}

    run_poll_task(monkeypatch, fake, [response])

    assert fake.sessions[1].status == "failed"


def test_poll_pause_and_resume_transitions(monkeypatch) -> None:
    """paused/resumed events drive the session status."""
    fake = FakeSession(
        sessions=[session_row()],
        projects=[project_row()],
    )
    paused = {"ts": "t1", "sessionId": "hc-abc123", "type": "paused"}
    resumed = {"ts": "t2", "sessionId": "hc-abc123", "type": "resumed"}

    pause_response = {"events": [paused], "nextOffset": 10}
    run_poll_task(monkeypatch, fake, [pause_response])
    assert fake.sessions[1].status == "paused"

    resume_response = {"events": [resumed], "nextOffset": 20}
    run_poll_task(monkeypatch, fake, [resume_response])
    assert fake.sessions[1].status == "running"


def test_poll_missing_session_is_noop(monkeypatch) -> None:
    """A vanished session row degrades to a noop before any HTTP call."""
    fake = FakeSession(sessions=[], projects=[])
    result = run_poll_task(monkeypatch, fake, [])

    assert result == {"status": "noop", "reason": "missing"}


def test_poll_not_running_is_noop(monkeypatch) -> None:
    """A completed session is not polled again."""
    fake = FakeSession(
        sessions=[session_row(status="completed")],
        projects=[project_row()],
    )
    result = run_poll_task(monkeypatch, fake, [])

    assert result == {"status": "noop", "reason": "not_running"}
    assert fake.added == []


def test_poll_missing_project_errors(monkeypatch) -> None:
    """A deleted project stops the poll (no repo to fetch events for)."""
    fake = FakeSession(
        sessions=[session_row()],
        projects=[project_row(deleted=True)],
    )
    result = run_poll_task(monkeypatch, fake, [])

    assert result == {"status": "error", "reason": "project_missing"}


def test_poll_feed_shrink_keeps_offset(monkeypatch) -> None:
    """A lower nextOffset (recreated feed) never rewinds the cursor."""
    fake = FakeSession(
        sessions=[session_row(event_offset=500)],
        projects=[project_row()],
    )
    response = {"sessionId": "hc-abc123", "events": [], "nextOffset": 0}

    result = run_poll_task(monkeypatch, fake, [response])

    assert result == {"status": "ok", "events": 0}
    assert fake.sessions[1].event_offset == 500
