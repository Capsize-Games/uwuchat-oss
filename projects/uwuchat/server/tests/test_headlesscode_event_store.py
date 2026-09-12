"""Tests for the headlesscode Redis outbox (append/drain).

Exercises the store against an in-memory fake Redis client — the real
Redis behavior (RPUSH/LPOP ordering, TTL) is the driver's, not ours.
"""

from __future__ import annotations

import pytest

from projects.uwuchat.server import headlesscode_event_store as store


class _FakeRedis:
    """In-memory stand-in for the outbox's cache_redis() client."""

    def __init__(self) -> None:
        self.list: list[str] = []
        self.expirations = 0

    def rpush(self, key: str, value: str) -> None:
        del key
        self.list.append(value)

    def expire(self, key: str, ttl: int) -> None:
        del key, ttl
        self.expirations += 1

    def lpop(self, key: str) -> str | None:
        del key
        if not self.list:
            return None
        return self.list.pop(0)


@pytest.fixture()
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    """Point the store's cache_redis() at an in-memory client."""
    fake = _FakeRedis()
    monkeypatch.setattr(store, "cache_redis", lambda: fake)
    return fake


def test_append_and_drain_roundtrip(fake_redis: _FakeRedis) -> None:
    """Appends drain oldest-first, and an empty outbox drains to []."""
    store.headlesscode_events_append({"a": 1})
    store.headlesscode_events_append({"b": 2})

    assert fake_redis.expirations == 2  # TTL refreshed per append
    assert store.headlesscode_events_drain() == [{"a": 1}, {"b": 2}]
    assert store.headlesscode_events_drain() == []


def test_drain_drops_malformed_entries(fake_redis: _FakeRedis) -> None:
    """A corrupt JSON entry is skipped, not fatal."""
    fake_redis.list.append("{not json")
    assert store.headlesscode_events_drain() == []


def test_drain_respects_limit(fake_redis: _FakeRedis) -> None:
    """Draining stops at *limit*; the rest stay queued."""
    for i in range(5):
        store.headlesscode_events_append({"i": i})

    drained = store.headlesscode_events_drain(limit=2)
    assert drained == [{"i": 0}, {"i": 1}]
    assert store.headlesscode_events_drain() == [
        {"i": 2}, {"i": 3}, {"i": 4},
    ]
