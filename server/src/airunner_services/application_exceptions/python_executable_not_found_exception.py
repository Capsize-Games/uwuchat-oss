"""Missing Python executable error."""


class PythonExecutableNotFoundException(Exception):
    """Raised when a configured Python executable cannot be located."""

    def __init__(self, message="Could not find python executable in venv"):
        self.message = message
        super().__init__(self.message)
