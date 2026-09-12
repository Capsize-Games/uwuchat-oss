"""Qt-compatible repeating timer."""

import threading
from typing import Optional

from airunner_services.utils.application.runtime_primitives.q_object import (
    QObject,
)
from airunner_services.utils.application.runtime_primitives.signal import (
    Signal,
)


class QTimer(QObject):
    """Simple repeating timer used for service-side background polling."""

    timeout = Signal()

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._interval_seconds = 0.0
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        super().__init__(*args, **kwargs)

    def start(self, milliseconds: int) -> None:
        """Start one repeating timer with the provided interval."""
        self.stop()
        self._interval_seconds = max(milliseconds, 0) / 1000
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        """Emit timeout callbacks until the timer is stopped."""
        while not self._stop_event.wait(self._interval_seconds):
            self.timeout.emit()

    def stop(self) -> None:
        """Stop the timer when it is active."""
        self._stop_event.set()

    def deleteLater(self) -> None:
        """Stop background timer work before dispatching destruction."""
        self.stop()
        super().deleteLater()
