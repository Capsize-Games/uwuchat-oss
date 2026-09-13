"""Tests for the headlesscode session-card conversation entry.

Covers ``headlesscode_card.append_session_card_entry`` plus the two
task-level card behaviors (stamp with a conversation id, skip without
one). All DB and broker interactions are mocked.
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


def _patch_dashboard(monkeypatch: pytest.MonkeyPatch):
    """Stub start_session/cache_redis; run coroutines for real."""
    import asyncio

    import projects.uwuchat.server.headlesscode_client as hc

    async def _start_session(**kwargs):
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
    monkeypatch.setattr(ht, "cache_redis", lambda: _FakeRedis())


def _fake_conversation_manager(monkeypatch: pytest.MonkeyPatch):
    """Return a manager stub; ``updates`` collects written values."""
    updates = []

    class _FakeConversation:
        id = 77
        value = [{"role": "user", "content": "hi"}]

    class _FakeObjects:
        def get(self, pk: int):
            assert pk == 77
            return _FakeConversation()

        def update(self, pk: int, **kwargs):
            assert pk == 77
            updates.append(kwargs["value"])
            return True

    class _FakeConversationManager:
        objects = _FakeObjects()

    import airunner_services.database.models.conversation as conv_mod

    monkeypatch.setattr(conv_mod, "Conversation", _FakeConversationManager)
    return updates


def test_append_entry_writes_card_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The appended entry carries every field the card needs."""
    from projects.uwuchat.server.headlesscode_card import (
        append_session_card_entry,
    )

    updates = _fake_conversation_manager(monkeypatch)
    append_session_card_entry(
        77, "hc-xyz", "running", "acme-web", "fix the login bug", "code",
    )
    assert len(updates) == 1
    entry = updates[0][-1]
    assert entry["metadata_type"] == "headlesscode_session"
    assert entry["headlesscode_session_id"] == "hc-xyz"
    assert entry["status"] == "running"
    assert entry["project_name"] == "acme-web"
    assert entry["task_description"] == "fix the login bug"
    assert entry["mode"] == "code"
    assert entry["role"] == "assistant"
    assert entry["content"] == ""
    assert "timestamp" in entry


def test_append_entry_noop_without_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """conversation_id None never touches the conversation module."""
    import airunner_services.database.models.conversation as conv_mod

    class _BoomObjects:
        def get(self, pk: int):
            raise AssertionError("must not be called")

    class _BoomManager:
        objects = _BoomObjects()

    monkeypatch.setattr(conv_mod, "Conversation", _BoomManager)
    from projects.uwuchat.server.headlesscode_card import (
        append_session_card_entry,
    )

    append_session_card_entry(
        None, "hc-xyz", "running", "acme-web", "task", None,
    )


def test_launch_task_appends_session_card_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A launch with a conversation id stamps the session card entry."""
    from projects.uwuchat.server.tasks.headlesscode_tasks import (
        launch_headlesscode_session_task,
    )

    project = SimpleNamespace(
        id=11, repo_path="/srv/acme", deleted=False,
    )
    fake = _FakeSession(project)
    _patch_scopes(monkeypatch, fake)
    _patch_dashboard(monkeypatch)
    updates = _fake_conversation_manager(monkeypatch)

    result = launch_headlesscode_session_task.apply(
        args=[
            11, 3, "fix the login bug", None, "tenant_x", 42, "idem-4",
            77, "acme-web",
        ],
    ).get()

    assert result == {"status": "started", "session_id": "hc-abc123"}
    row = fake.added[0]
    assert row.conversation_id == 77
    assert len(updates) == 1
    entry = updates[0][-1]
    assert entry["metadata_type"] == "headlesscode_session"
    assert entry["headlesscode_session_id"] == "hc-abc123"
    assert entry["status"] == "running"
    assert entry["project_name"] == "acme-web"
    assert entry["task_description"] == "fix the login bug"
    assert entry["role"] == "assistant"


def test_launch_task_without_conversation_skips_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No conversation id → session row persists, no card entry."""
    from projects.uwuchat.server.tasks.headlesscode_tasks import (
        launch_headlesscode_session_task,
    )

    project = SimpleNamespace(
        id=11, repo_path="/srv/acme", deleted=False,
    )
    fake = _FakeSession(project)
    _patch_scopes(monkeypatch, fake)
    _patch_dashboard(monkeypatch)

    import airunner_services.database.models.conversation as conv_mod

    class _BoomObjects:
        def get(self, pk: int):
            raise AssertionError("card append must be skipped")

    class _BoomConversationManager:
        objects = _BoomObjects()

    monkeypatch.setattr(conv_mod, "Conversation", _BoomConversationManager)

    result = launch_headlesscode_session_task.apply(
        args=[
            11, 3, "fix the login bug", None, "tenant_x", 42, "idem-5",
        ],
    ).get()

    assert result == {"status": "started", "session_id": "hc-abc123"}
    assert len(fake.added) == 1
