"""Qt-compatible thread wrapper."""

import threading
import time
from typing import Optional

from airunner_services.utils.application.runtime_primitives.q_object import (
    QObject,
)
from airunner_services.utils.application.runtime_primitives.signal import (
    Signal,
)


class QThread(QObject):
    """Small thread wrapper compatible with the old Qt worker API."""

    started = Signal()
    finished = Signal()

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._thread: Optional[threading.Thread] = None
        super().__init__(*args, **kwargs)

    def start(self) -> None:
        """Start one daemon thread unless it is already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """Emit start and finish notifications around thread work."""
        try:
            self.started.emit()
        finally:
            self.finished.emit()

    def quit(self) -> None:
        """Keep the Qt-compatible API surface for worker shutdown."""

    @staticmethod
    def msleep(milliseconds: int) -> None:
        """Sleep for the requested number of milliseconds."""
        time.sleep(max(milliseconds, 0) / 1000)
