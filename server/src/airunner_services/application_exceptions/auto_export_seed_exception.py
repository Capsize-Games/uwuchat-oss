"""Auto-export without a stable seed error."""


class AutoExportSeedException(Exception):
    """Raised when auto export is requested without a stable seed."""

    def __init__(
        self, message="Seed must be set when auto exporting an image"
    ):
        self.message = message
        super().__init__(self.message)
