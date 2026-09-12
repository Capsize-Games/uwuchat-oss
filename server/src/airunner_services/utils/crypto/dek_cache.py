"""Process-local, TTL-bound DEK cache for active user sessions.

The DEK is unwrapped once at login and held in memory for the lifetime
of the access token (default 15 min), with sliding expiry on each
authenticated request.  This avoids re-deriving the KEK from the password
(which the server never persists) on every request.

IMPORTANT: This cache is per-process.  The current deployment runs a
single server process; if the deployment ever moves to multiple replicas,
this cache must move to a shared store (Redis) or sessions must be sticky
to one replica.
"""

from __future__ import annotations

import contextlib
import threading
import time
from contextvars import ContextVar, Token

# Per-request DEK contextvar — set by the auth middleware after
# reading from the cache, cleared in the finally block of every request.
# Follows the same pattern as ``_tenant_key`` in airunner_services/data/tenant.py.
_user_dek: ContextVar[bytes | None] = ContextVar(
    "airunner_user_dek",
    default=None,
)


def set_user_dek(dek: bytes | None) -> Token[bytes | None]:
    """Store the DEK in context-local state for the current request."""
    return _user_dek.set(dek)


def reset_user_dek(token: Token[bytes | None]) -> None:
    """Restore the previous DEK contextvar token."""
    _user_dek.reset(token)


def get_user_dek() -> bytes | None:
    """Return the DEK for the current request, or None."""
    return _user_dek.get()


@contextlib.contextmanager
def dek_scope(dek: bytes | None):
    """Activate one DEK for the duration of a block.

    Always restores the previous value on exit — including when
    ``dek`` is ``None`` — so the contextvar cannot leak across
    reused threads (e.g. the long-lived LLM worker queue thread
    that processes requests for many users in sequence). Mirrors
    ``tenant_scope`` in ``airunner_services.data.tenant``.
    """
    token = set_user_dek(dek)
    try:
        yield
    finally:
        reset_user_dek(token)


# ── Process-local cache ──────────────────────────────────────────────


class _DekCache:
    """Thread-safe, TTL-bound cache mapping account_id → DEK."""

    def __init__(self, default_ttl: int = 900) -> None:
        """*default_ttl* in seconds (matches access token TTL, 15 min)."""
        self._lock = threading.Lock()
        self._entries: dict[int, tuple[bytes, float]] = {}
        self._default_ttl = default_ttl

    def get(self, account_id: int) -> bytes | None:
        """Return the cached DEK if present and not expired."""
        with self._lock:
            entry = self._entries.get(account_id)
            if entry is None:
                return None
            dek, expires_at = entry
            if time.monotonic() > expires_at:
                del self._entries[account_id]
                return None
            return dek

    def set(self, account_id: int, dek: bytes, ttl: int | None = None) -> None:
        """Store a DEK with optional TTL override."""
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._entries[account_id] = (dek, time.monotonic() + ttl)

    def touch(self, account_id: int) -> bool:
        """Extend the TTL for an existing entry (sliding expiry)."""
        with self._lock:
            entry = self._entries.get(account_id)
            if entry is None:
                return False
            dek, _ = entry
            if time.monotonic() > entry[1]:
                del self._entries[account_id]
                return False
            self._entries[account_id] = (
                dek,
                time.monotonic() + self._default_ttl,
            )
            return True

    def evict(self, account_id: int) -> None:
        """Remove an entry immediately (logout, token-version bump)."""
        with self._lock:
            self._entries.pop(account_id, None)


# Singleton instance — one per process.
_dek_cache = _DekCache()


def cache_get(account_id: int) -> bytes | None:
    """Return the cached DEK for *account_id*, or None."""
    return _dek_cache.get(account_id)


def cache_set(account_id: int, dek: bytes) -> None:
    """Store the DEK in the process cache."""
    _dek_cache.set(account_id, dek)


def cache_touch(account_id: int) -> bool:
    """Refresh the TTL for *account_id*. Returns False if not found."""
    return _dek_cache.touch(account_id)


def cache_evict(account_id: int) -> None:
    """Remove the DEK for *account_id* from the cache."""
    _dek_cache.evict(account_id)


__all__ = [
    "cache_evict",
    "cache_get",
    "cache_set",
    "cache_touch",
    "dek_scope",
    "get_user_dek",
    "reset_user_dek",
    "set_user_dek",
]
