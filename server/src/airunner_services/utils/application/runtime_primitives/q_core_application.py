"""Qt-compatible application singleton."""

from typing import Optional

from airunner_services.utils.application.runtime_primitives.q_object import (
    QObject,
)


class QCoreApplication(QObject):
    """Application singleton used by the service layer."""

    _instance: Optional["QCoreApplication"] = None

    def __init__(self, _args: Optional[list[object]] = None) -> None:
        del _args
        super().__init__()
        self._quit_requested = False
        self.__class__._instance = self

    @classmethod
    def instance(cls) -> Optional["QCoreApplication"]:
        """Return the currently active application instance."""
        return cls._instance

    def processEvents(self) -> None:
        """Keep the Qt-compatible event processing hook as a no-op."""

    def quit(self) -> None:
        """Record one quit request for compatibility with old code paths."""
        self._quit_requested = True
