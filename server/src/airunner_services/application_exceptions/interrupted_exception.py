"""Intentional interruption error."""


class InterruptedException(Exception):
    """Raised when work is intentionally interrupted."""

    def __init__(self, message="Interrupted"):
        self.message = message
        super().__init__(self.message)
