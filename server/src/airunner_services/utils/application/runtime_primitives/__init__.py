"""Service-owned runtime primitives, one class per file.

These avoid direct Qt dependencies while keeping the legacy worker API
surface compatible.
"""

from airunner_services.utils.application.runtime_primitives._bound_signal import (
    _BoundSignal,
)
from airunner_services.utils.application.runtime_primitives.q_core_application import (
    QCoreApplication,
)
from airunner_services.utils.application.runtime_primitives.q_object import (
    QObject,
)
from airunner_services.utils.application.runtime_primitives.q_thread import (
    QThread,
)
from airunner_services.utils.application.runtime_primitives.q_timer import (
    QTimer,
)
from airunner_services.utils.application.runtime_primitives.signal import (
    Signal,
)
from airunner_services.utils.application.runtime_primitives.slot import Slot

QApplication = QCoreApplication

__all__ = [
    "_BoundSignal",
    "QApplication",
    "QCoreApplication",
    "QObject",
    "QThread",
    "QTimer",
    "Signal",
    "Slot",
]
