"""Callbacks storage for one signal bound to one object instance."""

import threading
from collections.abc import Callable
from typing import Any


class _BoundSignal:
    """Store callbacks for one signal bound to one object instance."""

    def __init__(self) -> None:
        self._callbacks: list[Callable[..., Any]] = []
        self._lock = threading.Lock()

    def connect(self, callback: Callable[..., Any]) -> None:
        """Register one callback when it is not already connected."""
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def disconnect(self, callback: Callable[..., Any]) -> None:
        """Remove one callback when it is present."""
        with self._lock:
            self._callbacks = [
                existing
                for existing in self._callbacks
                if existing != callback
            ]

    def emit(self, *args: Any, **kwargs: Any) -> None:
        """Invoke each connected callback with the provided payload."""
        with self._lock:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            callback(*args, **kwargs)
