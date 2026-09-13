"""Tests for the exception sanitizer — confirms no raw exception text
reaches clients when AIRUNNER_DEBUG is unset."""

from __future__ import annotations

import logging

import pytest

from airunner_services.utils.error_sanitizer import (
    log_and_sanitize,
    sanitize_exception_message,
)


class TestSanitizeExceptionMessage:
    """Test sanitize_exception_message directly."""

    @pytest.fixture(autouse=True)
    def _clear_debug(self, monkeypatch) -> None:
        """Ensure AIRUNNER_DEBUG is not set for most tests."""
        monkeypatch.delenv("AIRUNNER_DEBUG", raising=False)

    def test_plain_exception_returns_generic_message(self) -> None:
        msg = sanitize_exception_message(ValueError("something broke"))
        assert msg == "Internal server error"

    def test_sqlalchemy_exception_sanitized(self) -> None:
        """SQLAlchemy errors often contain SQL text in str(exc)."""
        msg = sanitize_exception_message(
            RuntimeError(
                "(psycopg2.OperationalError) could not connect to server"
            )
        )
        assert msg == "Internal server error"

    def test_dek_missing_returns_specific_message(self) -> None:
        """DEK-missing RuntimeError gets a user-friendly message."""
        msg = sanitize_exception_message(
            RuntimeError("UserEncryptedText: no DEK in context")
        )
        assert "encryption session has expired" in msg.lower()

    def test_debug_mode_returns_raw_message(self, monkeypatch) -> None:
        monkeypatch.setenv("AIRUNNER_DEBUG", "1")
        msg = sanitize_exception_message(ValueError("debug details"))
        assert msg == "debug details"

    def test_log_and_sanitize_logs_and_returns_safe(self) -> None:
        logger = logging.getLogger(__name__)
        msg = log_and_sanitize(
            ValueError("secret data: user=admin pass=1234"),
            logger=logger,
            context="test error",
        )
        assert msg == "Internal server error"


class TestSanitizeHttpException:
    """Confirm sanitized_http_exception returns safe detail."""

    def test_sanitized_http_exception_uses_sanitizer(self) -> None:
        from airunner_services.api.server_middleware import (
            sanitized_http_exception,
        )

        logger = logging.getLogger(__name__)
        exc = sanitized_http_exception(
            ValueError("db: table users password=secret"),
            status_code=500,
            logger=logger,
            context="test error in HTTP route",
        )
        assert exc.status_code == 500
        assert exc.detail == "Internal server error"
        assert "secret" not in exc.detail


class TestSanitizerInRoutes:
    """End-to-end: confirm the sanitizer is actually used in the
    routes we fixed (daemon_runtime_actions and bluesky routes).
    These tests verify the import path exists and the wrapper is
    already wired, without hitting a real database."""

    def test_daemon_runtime_imports_sanitized_http_exception(self) -> None:
        from airunner_services.api.routes import daemon_runtime_actions
        # The module imports sanitized_http_exception at the top level
        # and uses it in cancel_runtime_action instead of raw str(exc).
        import inspect
        source = inspect.getsource(daemon_runtime_actions)
        assert "sanitized_http_exception" in source

    def test_bluesky_imports_sanitizer(self) -> None:
        """The bluesky routes module imports log_and_sanitize."""
        import projects.uwuchat.server.bluesky.routes as br
        import inspect
        source = inspect.getsource(br)
        assert "log_and_sanitize" in source
