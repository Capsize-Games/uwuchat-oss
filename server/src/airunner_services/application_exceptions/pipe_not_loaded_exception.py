"""Missing art pipeline error."""


class PipeNotLoadedException(Exception):
    """Raised when a required art pipeline has not been loaded yet."""

    def __init__(self, message="Pipe not loaded"):
        self.message = message
        super().__init__(self.message)
