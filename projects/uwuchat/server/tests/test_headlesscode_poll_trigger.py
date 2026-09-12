"""Tests for the headlesscode Beat trigger and polling helpers.

The trigger enumerates active sessions and enqueues one poll task per
session (mirroring the email sync trigger); the direct helper tests
cover the status-transition mapping. Shared fakes live in
``fakes_headlesscode``.
"""

from __future__ import annotations

from decimal import Decimal

from projects.uwuchat.server.tests.fakes_headlesscode import (
    FakeSession,
    noop_scope,
    session_row,
)


def test_trigger_enqueues_poll_per_active_session(
    monkeypatch,
) -> None:
    """The Beat trigger enqueues one poll task per tenant."""
    import airunner_services.data.tenant as tenant_mod

    from projects.uwuchat.server.tasks import headlesscode_poll_tasks as mod

    enqueued: list[list] = []
    monkeypatch.setattr(
        mod, "_list_tenant_schemas", lambda: ["tenant_a", "tenant_b"],
    )
    monkeypatch.setattr(tenant_mod, "tenant_key_from_schema", lambda s: s)
    monkeypatch.setattr(tenant_mod, "tenant_scope", noop_scope)
    monkeypatch.setattr(
        mod, "_enqueue_running_sessions",
        lambda tk: enqueued.append(tk) or 1,
    )

    result = mod.trigger_headlesscode_session_polling.apply().get()

    assert result == {"enqueued": 2}
    assert enqueued == ["tenant_a", "tenant_b"]


def test_enqueue_active_sessions_dispatches_rows(monkeypatch) -> None:
    """Every row the query returns gets a poll task with its tenant."""
    import airunner_services.database.session as session_mod

    from projects.uwuchat.server.tasks import headlesscode_poll_tasks as mod

    fake = FakeSession(
        sessions=[
            session_row(id=1),
            session_row(id=2),
            session_row(id=3, status="paused"),
        ],
        projects=[],
    )
    monkeypatch.setattr(
        session_mod, "session_scope",
        lambda: noop_scope(fake),
    )
    enqueued_args: list[list] = []
    monkeypatch.setattr(
        mod.poll_headlesscode_session_task,
        "apply_async",
        lambda **kw: enqueued_args.append(kw["args"]),
    )

    assert mod._enqueue_running_sessions("tenant_a") == 3
    assert enqueued_args == [[1, "tenant_a"], [2, "tenant_a"],
                             [3, "tenant_a"]]


def test_enqueue_active_sessions_no_rows_returns_zero(
    monkeypatch,
) -> None:
    """A tenant with no active sessions enqueues nothing."""
    import airunner_services.database.session as session_mod

    from projects.uwuchat.server.tasks import headlesscode_poll_tasks as mod

    fake = FakeSession(sessions=[], projects=[])
    monkeypatch.setattr(
        session_mod, "session_scope",
        lambda: noop_scope(fake),
    )
    enqueued_args: list[list] = []
    monkeypatch.setattr(
        mod.poll_headlesscode_session_task,
        "apply_async",
        lambda **kw: enqueued_args.append(kw["args"]),
    )

    assert mod._enqueue_running_sessions("tenant_a") == 0
    assert enqueued_args == []


def test_apply_status_transitions_direct() -> None:
    """Pause/resume/terminal transitions map to session statuses."""
    from projects.uwuchat.server.headlesscode_polling import (
        apply_status_transitions,
    )

    row = session_row()
    changed, cost = apply_status_transitions(row, [
        {"type": "paused"},
        {"type": "resumed"},
        {"type": "session_end", "status": "success", "costUsd": 1.25},
    ])
    assert changed == "completed"
    assert cost == Decimal("1.25")
    assert row.status == "completed"


def test_apply_status_transitions_ignores_resume_on_running() -> None:
    """A resume without a pause is a no-op status change."""
    from projects.uwuchat.server.headlesscode_polling import (
        apply_status_transitions,
    )

    row = session_row()
    changed, cost = apply_status_transitions(row, [
        {"type": "resumed"},
    ])
    assert changed is None
    assert cost is None
    assert row.status == "running"
