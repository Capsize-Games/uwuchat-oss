"""Thread-safe TTL cache for FastSearch newspaper markdown."""

from __future__ import annotations

import threading
import time
from typing import Optional


_DEFAULT_TTL: int = 900  # 15 minutes


class NewspaperCache:
    """In-memory TTL cache for FastSearch newspaper markdown.

    Caches the full markdown newspaper keyed by a user/session identifier
    plus an optional compact snapshot for per-turn context injection.
    Thread-safe.
    """

    def __init__(self, ttl: int = _DEFAULT_TTL) -> None:
        """Initialise the cache.

        Args:
            ttl: Cache time-to-live in seconds.  Default 900 (15 min).
        """
        self._ttl = ttl
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, str]] = {}
        self._snapshots: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str = "default") -> Optional[str]:
        """Return cached markdown for *key*, or None if expired/missing.

        Args:
            key: Cache key (e.g. ``"default"``, ``"user_42"``).

        Returns:
            Markdown string or ``None``.
        """
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            ts, markdown = entry
            if time.time() - ts > self._ttl:
                del self._entries[key]
                return None
            return markdown

    def set(
        self,
        key: str,
        markdown: str,
        snapshot: str | None = None,
    ) -> None:
        """Store *markdown* under *key* with the current timestamp.

        Args:
            key: Cache key.
            markdown: Full newspaper markdown.
            snapshot: Optional compact snapshot for per-turn injection
                (keyed by the same *key* as the full entry).
        """
        with self._lock:
            self._entries[key] = (time.time(), markdown)
            if snapshot is not None:
                self._snapshots[key] = snapshot

    def get_snapshot(self, key: str = "default") -> Optional[str]:
        """Return the compact snapshot for *key*, or None if not set.

        Args:
            key: Cache key matching the one used in :meth:`set`.

        Returns:
            Snapshot string or ``None``.
        """
        with self._lock:
            return self._snapshots.get(key)

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._entries.clear()
            self._snapshots.clear()

    def clear_expired(self) -> None:
        """Evict entries whose TTL has elapsed."""
        now = time.time()
        with self._lock:
            expired = [
                k for k, (ts, _) in self._entries.items()
                if now - ts > self._ttl
            ]
            for k in expired:
                del self._entries[k]
                self._snapshots.pop(k, None)
