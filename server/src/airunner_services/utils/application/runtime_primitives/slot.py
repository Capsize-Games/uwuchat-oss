"""Qt-compatible slot decorator."""

from collections.abc import Callable


def Slot(*_args: object, **_kwargs: object) -> Callable[[Callable], Callable]:
    """Return a no-op decorator compatible with Qt slot annotations."""

    def _decorator(function: Callable) -> Callable:
        return function

    return _decorator
