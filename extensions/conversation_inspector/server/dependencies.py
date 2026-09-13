"""Conversation Flow Inspector — FastAPI dependencies.

Reuses the auth extension's ``require_superuser`` to gate all admin
endpoints behind superuser authentication.
"""

from extensions.auth.server.dependencies import require_superuser

__all__ = ["require_superuser"]
