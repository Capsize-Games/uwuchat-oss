"""Shared fakes for the headlesscode poll/trigger test files.

The poll-cycle tests (test_headlesscode_poll_tasks.py) and the trigger
tests (test_headlesscode_poll_trigger.py) exercise the same mocked
scopes, dashboard client, outbox, and credit-settlement — the stubs
live here so both files stay under the 250-line limit. All DB and
Redis interactions are mocked: no real tenant schema, Redis, or
dashboard needed.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import Any

import pytest

from projects.uwuchat.server.models.headlesscode_project import (
    HeadlesscodeProject,
)
from projects.uwuchat.server.models.headlesscode_session import (
    HeadlesscodeSession,
)


def session_row(**kwargs) -> SimpleNamespace:
    """Build a fake headlesscode_sessions row."""
    defaults = {
        "id": 1, "project_id": 11, "deleted": False,
        "status": "running", "headlesscode_session_id": "hc-abc123",
        "event_offset": 0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def project_row(**kwargs) -> SimpleNamespace:
    """Build a fake headlesscode_projects row."""
    defaults = {
        "id": 11, "user_id": 42, "deleted": False,
        "repo_path": "/srv/acme",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class FakeQuery:
    """Query stub: ``get`` from a map; ``filter/order_by`` ignored."""

    def __init__(self, rows: list, get_map: dict | None = None):
        self._rows = rows
        self._get_map = get_map or {}

    def get(self, pk: int):
        return self._get_map.get(pk)

    def filter(self, *expr):
        return self

    def order_by(self, *expr):
        return self

    def all(self):
        return self._rows


class FakeSession:
    """Session stub capturing added rows and serving pre-set rows."""

    def __init__(
        self,
        sessions: list | None = None,
        projects: list | None = None,
        stored_events: list | None = None,
    ) -> None:
        self.sessions = {r.id: r for r in (sessions or [])}
        self.projects = {r.id: r for r in (projects or [])}
        self.stored_events = stored_events or []
        self.added = []

    def query(self, cls):
        model = getattr(cls, "class_", cls)
        if model is HeadlesscodeSession:
            return FakeQuery(
                [(r.id,) for r in self.sessions.values()],
                self.sessions,
            )
        if model is HeadlesscodeProject:
            return FakeQuery(
                [(r.id,) for r in self.projects.values()],
                self.projects,
            )
        return FakeQuery([(e,) for e in self.stored_events])

    def add(self, row) -> None:
        self.added.append(row)

    def commit(self) -> None:
        pass


class ExpiringFakeSession(FakeSession):
    """FakeSession whose ``commit()`` expires and detaches loaded rows.

    The real ``session_scope`` commits with ``expire_on_commit=True``
    (every ORM attribute is expired) and then calls
    ``Session.remove()`` (instances become detached), so reading any
    attribute off a previously loaded row afterwards raises
    ``DetachedInstanceError``. This fake mirrors that by deleting every
    attribute off the loaded rows in ``commit()``: any post-commit read
    raises ``AttributeError``, catching the same class of bug (a
    post-commit ORM read) that the real exception does. The poll task
    must capture every value it needs before ``commit()``.
    """

    @staticmethod
    def _expire_row(row: Any) -> None:
        for name in list(vars(row)):
            delattr(row, name)

    def commit(self) -> None:
        rows = list(self.sessions.values()) + list(self.projects.values())
        for row in rows:
            self._expire_row(row)


@contextlib.contextmanager
def noop_scope(*_args, **_kwargs):
    """Context manager yielding its first arg (tenant_scope stand-in)."""
    yield _args[0] if _args else None


def patch_scopes(
    monkeypatch: pytest.MonkeyPatch, fake: FakeSession,
) -> None:
    """Point tenant_scope/session_scope at no-op/fake implementations."""
    import airunner_services.data.tenant as tenant_mod
    import airunner_services.database.session as session_mod

    @contextlib.contextmanager
    def _tenant_scope(key):
        yield

    @contextlib.contextmanager
    def _session_scope():
        yield fake

    monkeypatch.setattr(tenant_mod, "tenant_scope", _tenant_scope)
    monkeypatch.setattr(session_mod, "session_scope", _session_scope)


def patch_dashboard(
    monkeypatch: pytest.MonkeyPatch, responses: list[dict],
) -> None:
    """Stub get_session_events; run coroutines for real."""
    import asyncio

    import projects.uwuchat.server.headlesscode_client as hc
    import projects.uwuchat.server.tasks.headlesscode_tasks as ht

    async def _get_session_events(session_id, repo, since=0):
        return responses.pop(0)

    monkeypatch.setattr(hc, "get_session_events", _get_session_events)

    def _run_async(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(ht, "_run_async", _run_async)


def patch_outbox(
    monkeypatch: pytest.MonkeyPatch, captured: list | None = None,
) -> list[dict]:
    """Capture headlesscode_events_append calls; return the payloads.

    Pass an existing *captured* list to share one capture across
    helpers (e.g. ``run_poll_task``) and the test body.
    """
    import projects.uwuchat.server.headlesscode_event_store as store

    captured = captured if captured is not None else []
    monkeypatch.setattr(
        store, "headlesscode_events_append", captured.append,
    )
    return captured


def patch_finalize(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Capture finalize_session_usage calls; return (args, kwargs)."""
    import projects.uwuchat.server.tasks.headlesscode_tasks as ht

    calls: list[tuple] = []
    monkeypatch.setattr(
        ht, "finalize_session_usage",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


def run_poll_task(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeSession,
    responses: list[dict],
    outbox: list | None = None,
) -> dict:
    """Run poll_headlesscode_session_task with all mocks in place.

    *outbox* (when given) receives the forwarded payloads; without it
    the outbox is patched to a throwaway list so no real Redis is
    touched.
    """
    from projects.uwuchat.server.tasks.headlesscode_poll_tasks import (
        poll_headlesscode_session_task,
    )

    patch_scopes(monkeypatch, fake)
    patch_dashboard(monkeypatch, responses)
    patch_outbox(monkeypatch, outbox)
    return poll_headlesscode_session_task.apply(
        args=[1, "tenant_x"],
    ).get()
