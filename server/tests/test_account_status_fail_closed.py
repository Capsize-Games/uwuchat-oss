"""Tests for fail-closed account-status check.

Part 5 (MEDIUM) — ``_check_account_status`` must raise (not return
``None``) when the database is unreachable, so a banned or suspended
account is never silently admitted during a transient DB hiccup.

Also tests the tuple return value (status, token_version) added in
round 13 for access-token revocation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from extensions.auth.server.middleware import _check_account_status


class TestAccountStatusFailClosed:
    """``_check_account_status`` raises on DB errors."""

    def test_db_exception_raises_runtime_error(self) -> None:
        """A database error raises RuntimeError (fail-closed)."""
        with patch(
            "airunner_services.database.session.public_session_scope",
            side_effect=Exception("connection refused"),
        ):
            with pytest.raises(RuntimeError) as exc_info:
                _check_account_status(42)
            assert "Database unreachable" in str(exc_info.value)
            assert "42" in str(exc_info.value)

    def test_active_account_returns_none_zero(self) -> None:
        """An active account returns (None, token_version)."""
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.deleted = False
        mock_account.is_banned = False
        mock_account.is_suspended = False
        mock_account.token_version = 7
        mock_session.__enter__.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_account
        )

        with patch(
            "airunner_services.database.session.public_session_scope",
            return_value=mock_session,
        ):
            status, ver = _check_account_status(7)
            assert status is None
            assert ver == 7

    def test_deleted_account_returns_deleted(self) -> None:
        """A deleted account returns ('deleted', 0)."""
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.deleted = True
        mock_session.__enter__.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_account
        )

        with patch(
            "airunner_services.database.session.public_session_scope",
            return_value=mock_session,
        ):
            status, ver = _check_account_status(42)
            assert status == "deleted"
            assert ver == 0

    def test_nonexistent_account_returns_deleted(self) -> None:
        """A nonexistent account returns ('deleted', 0)."""
        mock_session = MagicMock()
        mock_session.__enter__.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = (
            None
        )

        with patch(
            "airunner_services.database.session.public_session_scope",
            return_value=mock_session,
        ):
            status, ver = _check_account_status(99999)
            assert status == "deleted"
            assert ver == 0

    def test_banned_account_returns_banned(self) -> None:
        """A banned account returns ('banned', token_version)."""
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.deleted = False
        mock_account.is_banned = True
        mock_account.is_suspended = False
        mock_account.token_version = 3
        mock_session.__enter__.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_account
        )

        with patch(
            "airunner_services.database.session.public_session_scope",
            return_value=mock_session,
        ):
            status, ver = _check_account_status(42)
            assert status == "banned"
            assert ver == 3

    def test_suspended_account_returns_suspended(self) -> None:
        """A suspended account returns ('suspended', token_version)."""
        mock_session = MagicMock()
        mock_account = MagicMock()
        mock_account.deleted = False
        mock_account.is_banned = False
        mock_account.is_suspended = True
        mock_account.token_version = 5
        mock_session.__enter__.return_value = mock_session
        mock_session.query.return_value.filter.return_value.first.return_value = (
            mock_account
        )

        with patch(
            "airunner_services.database.session.public_session_scope",
            return_value=mock_session,
        ):
            status, ver = _check_account_status(42)
            assert status == "suspended"
            assert ver == 5
