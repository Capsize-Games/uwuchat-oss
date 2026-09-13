"""Process-local, TTL-bound cache for deserialized FHE secret contexts.

Mirrors :mod:`airunner_services.utils.crypto.dek_cache` in shape:
process-local dict keyed by ``account_id``, ContextVar for the
current request, 15-minute sliding TTL, evicted on logout.

Caching the **deserialized** context (not just wrapped bytes) avoids
repeating the non-trivial cost of deserializing SEAL parameters on
every tool call within a session.
"""
from __future__ import annotations

import contextlib
import threading
import time
from contextvars import ContextVar, Token
from typing import Any

# Per-request FHE context contextvar — populated on first use,
# cleared at the end of every request.  Mirrors the DEK pattern.
_fhe_context: ContextVar[Any | None] = ContextVar(
    "airunner_fhe_context",
    default=None,
)


def set_fhe_context(ctx) -> Token:
    """Store the FHE secret context in context-local state."""
    return _fhe_context.set(ctx)


def reset_fhe_context(token: Token) -> None:
    """Restore the previous FHE context contextvar token."""
    _fhe_context.reset(token)


def get_fhe_context():
    """Return the FHE secret context for the current request, or None."""
    return _fhe_context.get()


@contextlib.contextmanager
def fhe_scope(ctx):
    """Activate one FHE context for the duration of a block.

    Always restores the previous value on exit so the contextvar
    cannot leak across reused threads.
    """
    token = set_fhe_context(ctx)
    try:
        yield
    finally:
        reset_fhe_context(token)


# ── Process-local cache ──────────────────────────────────────────


class _FheContextCache:
    """Thread-safe, TTL-bound cache mapping account_id → secret context."""

    def __init__(self, default_ttl: int = 900) -> None:
        """*default_ttl* in seconds (matches access token TTL, 15 min)."""
        self._lock = threading.Lock()
        self._entries: dict[int, tuple[Any, float]] = {}
        self._default_ttl = default_ttl

    def get(self, account_id: int):
        """Return the cached secret context if present and not expired."""
        with self._lock:
            entry = self._entries.get(account_id)
            if entry is None:
                return None
            ctx, expires_at = entry
            if time.monotonic() > expires_at:
                del self._entries[account_id]
                return None
            return ctx

    def set(self, account_id: int, ctx, ttl: int | None = None) -> None:
        """Store a secret context with optional TTL override."""
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._entries[account_id] = (ctx, time.monotonic() + ttl)

    def touch(self, account_id: int) -> bool:
        """Extend the TTL for an existing entry (sliding expiry)."""
        with self._lock:
            entry = self._entries.get(account_id)
            if entry is None:
                return False
            ctx, expires_at = entry
            if time.monotonic() > expires_at:
                del self._entries[account_id]
                return False
            self._entries[account_id] = (
                ctx,
                time.monotonic() + self._default_ttl,
            )
            return True

    def evict(self, account_id: int) -> None:
        """Remove an entry immediately (logout, token-version bump)."""
        with self._lock:
            self._entries.pop(account_id, None)


# Singleton instance — one per process.
_fhe_context_cache = _FheContextCache()


def fhe_cache_get(account_id: int):
    """Return the cached secret context for *account_id*, or None."""
    return _fhe_context_cache.get(account_id)


def fhe_cache_set(account_id: int, ctx) -> None:
    """Store the secret context in the process cache."""
    _fhe_context_cache.set(account_id, ctx)


def fhe_cache_touch(account_id: int) -> bool:
    """Refresh the TTL for *account_id*. Returns False if not found."""
    return _fhe_context_cache.touch(account_id)


def fhe_cache_evict(account_id: int) -> None:
    """Remove the secret context for *account_id* from the cache."""
    _fhe_context_cache.evict(account_id)


__all__ = [
    "fhe_cache_evict",
    "fhe_cache_get",
    "fhe_cache_set",
    "fhe_cache_touch",
    "fhe_scope",
    "get_fhe_context",
    "reset_fhe_context",
    "set_fhe_context",
]
