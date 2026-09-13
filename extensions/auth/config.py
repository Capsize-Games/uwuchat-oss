"""Extension configuration for the Auth extension."""

from airunner_services.extensions.config import ExtensionConfig


class AuthExtension(ExtensionConfig):
    name = "auth"
    label = "Authentication"
    description = (
        "User registration, login, and JWT-based authentication"
    )
