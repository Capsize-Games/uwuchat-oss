"""Minimal Qt-compatible object base."""

from airunner_services.utils.application.runtime_primitives.signal import (
    Signal,
)


class QObject:
    """Minimal object API used by service-owned runtime code."""

    destroyed = Signal()

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._object_name = ""
        self._thread = None
        super().__init__(*args, **kwargs)

    def setObjectName(self, name: str) -> None:
        """Store one object name for diagnostics compatibility."""
        self._object_name = name

    def objectName(self) -> str:
        """Return the currently stored object name."""
        return self._object_name

    def moveToThread(self, thread: object) -> None:
        """Keep the legacy worker API surface without Qt affinity."""
        self._thread = thread

    def thread(self) -> object | None:
        """Return the thread reference last assigned to this object."""
        return self._thread

    def deleteLater(self) -> None:
        """Emit destruction callbacks immediately in service mode."""
        self.destroyed.emit()
