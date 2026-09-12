"""Shared sanitization for exception text sent to clients.

Exceptions (especially SQLAlchemy/psycopg errors) can embed SQL text,
bound parameters, file paths, or other internals. Nothing derived from
``str(exc)`` may reach a client directly — log the full exception
server-side and return a generic message instead, gated by
``AIRUNNER_DEBUG`` for local troubleshooting only.
"""

from __future__ import annotations

import logging
import os


def sanitize_exception_message(exc: Exception) -> str:
    """Return a client-safe message for *exc*."""
    debug = os.environ.get("AIRUNNER_DEBUG", "0") == "1"
    if debug:
        return str(exc)
    if _is_dek_missing_error(exc):
        return (
            "Your encryption session has expired. "
            "Please log out and back in to continue."
        )
    return "Internal server error"


def sanitize_exception_code(exc: Exception) -> str | None:
    """Return a stable machine-readable error code for *exc*, or None.

    The client uses this to react programmatically (e.g. force logout)
    rather than pattern-matching human-readable prose.
    """
    if _is_dek_missing_error(exc):
        return "encryption_session_expired"
    return None


def _is_dek_missing_error(exc: Exception) -> bool:
    """Return True when *exc* is the DEK-not-cached RuntimeError.

    Raised by ``UserEncryptedText.process_bind_param`` when no
    per-request DEK is available.  The message is a developer-authored
    string with no SQL, bound parameters, or internal paths — we check
    the message prefix rather than importing from the crypto module to
    avoid a circular dependency.
    """
    return bool(
        isinstance(exc, RuntimeError)
        and exc.args
        and isinstance(exc.args[0], str)
        and exc.args[0].startswith("UserEncryptedText:")
    )


def log_and_sanitize(
    exc: Exception,
    *,
    logger: logging.Logger,
    context: str,
) -> str:
    """Log the full exception, return the sanitized client message."""
    logger.error("%s: %s", context, exc, exc_info=True)
    return sanitize_exception_message(exc)
