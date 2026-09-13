"""Missing prompt template error."""


class PromptTemplateNotFoundExeption(Exception):
    """Raised when a referenced prompt template cannot be found."""

    def __init__(self, message="Prompt template not found"):
        self.message = message
        super().__init__(self.message)
