"""NaN detection error."""


class NaNException(Exception):
    """Raised when NaN values are detected in generated data."""

    def __init__(self, message="NaN values found"):
        self.message = message
        super().__init__(self.message)
