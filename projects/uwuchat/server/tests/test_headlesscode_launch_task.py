"""Tests for the headlesscode Celery launch task itself.

Split out of test_headlesscode_tasks.py (which keeps the credit-ledger
wiring test) to stay under CLAUDE.md's 250-line file limit. All DB and
Redis interactions are mocked — no real tenant schema or Redis needed.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace

import pytest

FIXED_RESPONSE = {
    "sessionId": "hc-abc123",
    "pid": 99,
    "workspace": "/srv/acme",
    "mode": "code",
}


class _FakeQuery:
    """Query stub whose ``get`` returns a fixed project or None."""

    def __init__(self, project):
        self._project = project

    def get(self, pk: int):
        return self._project


class _FakeSession:
    """Session stub capturing added rows and serving one project."""

    def __init__(self, project):
        self._project = project
        self.added = []

    def query(self, cls):
        del cls
        return _FakeQuery(self._project)

    def add(self, row) -> None:
        self.added.append(row)

    def commit(self) -> None:
        pass


def _patch_scopes(monkeypatch: pytest.MonkeyPatch, fake: _FakeSession):
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


class _FakeRedis:
    """In-memory stand-in for the launch-marker cache_redis() client."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        del ex
        self.store[key] = value


def _patch_dashboard(
    monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis | None = None,
):
    """Stub start_session/cache_redis; run coroutines for real."""
    import asyncio

    import projects.uwuchat.server.headlesscode_client as hc

    started = []

    async def _start_session(**kwargs):
        started.append(kwargs)
        return FIXED_RESPONSE

    monkeypatch.setattr(hc, "start_session", _start_session)
    import projects.uwuchat.server.tasks.headlesscode_tasks as ht

    def _run_async(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    monkeypatch.setattr(ht, "_run_async", _run_async)
    monkeypatch.setattr(
        ht, "cache_redis", lambda: fake_redis or _FakeRedis(),
    )
    return started


def test_launch_task_persists_session_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful launch writes a RUNNING row with the real id."""
    from projects.uwuchat.server.tasks.headlesscode_tasks import (
        launch_headlesscode_session_task,
    )

    project = SimpleNamespace(
        id=11, repo_path="/srv/acme", deleted=False,
    )
    fake = _FakeSession(project)
    _patch_scopes(monkeypatch, fake)
    _patch_dashboard(monkeypatch)

    result = launch_headlesscode_session_task.apply(
        args=[
            11, 3, "fix the login bug", None, "tenant_x", 42, "idem-1",
        ],
    ).get()

    assert result == {"status": "started", "session_id": "hc-abc123"}
    assert len(fake.added) == 1
    row = fake.added[0]
    assert row.headlesscode_session_id == "hc-abc123"
    assert row.status == "running"
    assert row.project_id == 11
    assert row.chatbot_id == 3
    assert row.task_description == "fix the login bug"
    assert row.mode == "code"
    assert row.conversation_id is None


def test_launch_task_missing_project_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deleted/unknown project is rejected before any HTTP call."""
    from projects.uwuchat.server.tasks.headlesscode_tasks import (
        launch_headlesscode_session_task,
    )

    fake = _FakeSession(None)
    _patch_scopes(monkeypatch, fake)
    started = _patch_dashboard(monkeypatch)

    result = launch_headlesscode_session_task.apply(
        args=[99, None, "fix bug", None, "tenant_x", 42, "idem-2"],
    ).get()

    assert result == {"status": "error", "reason": "project_missing"}
    assert fake.added == []
    assert started == []


def test_launch_task_recovers_session_id_on_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retry after a persist failure reuses the same session id.

    Simulates: start_session already succeeded and the marker was set
    (e.g. by an earlier attempt), so this run must NOT call
    start_session again — it should recover hc-abc123 from the
    marker and just (re)persist the row.
    """
    from projects.uwuchat.server.tasks.headlesscode_tasks import (
        _launch_marker_key,
        launch_headlesscode_session_task,
    )

    project = SimpleNamespace(
        id=11, repo_path="/srv/acme", deleted=False,
    )
    fake = _FakeSession(project)
    _patch_scopes(monkeypatch, fake)
    fake_redis = _FakeRedis()
    fake_redis.store[_launch_marker_key("idem-3")] = "hc-abc123"
    started = _patch_dashboard(monkeypatch, fake_redis)

    result = launch_headlesscode_session_task.apply(
        args=[11, 3, "fix the login bug", None, "tenant_x", 42, "idem-3"],
    ).get()

    assert result == {"status": "started", "session_id": "hc-abc123"}
    assert started == []  # start_session was NOT called again
    assert len(fake.added) == 1
