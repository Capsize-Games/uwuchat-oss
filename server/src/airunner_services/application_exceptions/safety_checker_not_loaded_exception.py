"""Unavailable safety checker error."""


class SafetyCheckerNotLoadedException(Exception):
    """Raised when the configured safety checker is unavailable."""

    def __init__(self, message="Safety checker not ready"):
        self.message = message
        super().__init__(self.message)
