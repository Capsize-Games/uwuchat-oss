"""Unit tests for DEK cache (dek_cache.py)."""

from __future__ import annotations


import pytest

from airunner_services.utils.crypto.dek_cache import (
    cache_evict,
    cache_get,
    cache_set,
    cache_touch,
    get_user_dek,
    reset_user_dek,
    set_user_dek,
)
from airunner_services.utils.crypto.user_envelope import generate_dek


@pytest.fixture()
def _dek() -> bytes:
    return generate_dek()


@pytest.fixture(autouse=True)
def _clean_cache():
    """Evict test entries so tests don't leak state."""
    yield
    cache_evict(1)
    cache_evict(2)


# ---------------------------------------------------------------------------
# cache_set / cache_get round-trip
# ---------------------------------------------------------------------------


def test_cache_set_get_round_trip(_dek):
    """cache_set -> cache_get returns the same DEK."""
    cache_set(1, _dek)
    assert cache_get(1) == _dek


def test_cache_get_missing_returns_none():
    """cache_get for an unset key returns None."""
    assert cache_get(999) is None


def test_cache_evict_removes_entry(_dek):
    """cache_evict removes the entry, get returns None."""
    cache_set(1, _dek)
    cache_evict(1)
    assert cache_get(1) is None


# ---------------------------------------------------------------------------
# TTL expiry and sliding touch
# ---------------------------------------------------------------------------


def test_cache_ttl_expiry(monkeypatch, _dek):
    """Entry expires after TTL and get returns None."""
    # Set with 0-second TTL so it expires immediately.
    from airunner_services.utils.crypto import dek_cache

    original_set = dek_cache._dek_cache.set

    def _set_with_ttl(account_id, dek_bytes, ttl=None):
        original_set(account_id, dek_bytes, ttl=0)

    monkeypatch.setattr(dek_cache._dek_cache, "set", _set_with_ttl)

    cache_set(1, _dek)
    # Force expiry by advancing time
    assert cache_get(1) is None


def test_cache_touch_extends_ttl(_dek):
    """cache_touch returns True for existing entry."""
    cache_set(1, _dek)
    assert cache_touch(1) is True
    assert cache_get(1) == _dek


def test_cache_touch_missing_returns_false():
    """cache_touch returns False for non-existent entry."""
    assert cache_touch(999) is False


def test_cache_touch_expired_returns_false(monkeypatch, _dek):
    """cache_touch returns False for expired entry."""
    from airunner_services.utils.crypto import dek_cache

    original_set = dek_cache._dek_cache.set

    def _set_with_ttl(account_id, dek_bytes, ttl=None):
        original_set(account_id, dek_bytes, ttl=0)

    monkeypatch.setattr(dek_cache._dek_cache, "set", _set_with_ttl)

    cache_set(1, _dek)
    assert cache_touch(1) is False


# ---------------------------------------------------------------------------
# contextvar helpers
# ---------------------------------------------------------------------------


def test_set_get_user_dek(_dek):
    """set_user_dek -> get_user_dek returns the DEK."""
    token = set_user_dek(_dek)
    try:
        assert get_user_dek() == _dek
    finally:
        reset_user_dek(token)


def test_get_user_dek_default_none():
    """get_user_dek returns None when not set."""
    assert get_user_dek() is None


def test_reset_user_dek_restores_previous(_dek):
    """reset_user_dek restores the previous value."""
    dek1 = _dek
    dek2 = generate_dek()

    token1 = set_user_dek(dek1)
    assert get_user_dek() == dek1

    token2 = set_user_dek(dek2)
    assert get_user_dek() == dek2

    # Reset second -> back to first
    reset_user_dek(token2)
    assert get_user_dek() == dek1

    # Reset first -> back to None
    reset_user_dek(token1)
    assert get_user_dek() is None
