"""Signal descriptor primitive."""

from typing import Any

from airunner_services.utils.application.runtime_primitives._bound_signal import (
    _BoundSignal,
)


class Signal:
    """Descriptor that exposes one bound signal per object instance."""

    def __init__(self, *_args: object) -> None:
        self._storage_name = ""

    def __set_name__(self, _owner: type, name: str) -> None:
        """Remember the instance attribute used for this bound signal."""
        self._storage_name = f"__service_signal_{name}"

    def __get__(self, instance: object, _owner: type | None = None) -> Any:
        """Return the descriptor on the class or one bound signal."""
        if instance is None:
            return self
        signal = getattr(instance, self._storage_name, None)
        if signal is None:
            signal = _BoundSignal()
            setattr(instance, self._storage_name, signal)
        return signal
