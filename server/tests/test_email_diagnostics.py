"""Tests for the email diagnostics script (Part 5).

Verifies the core query functions return the correct shape against
a mocked database session.

Note: the diagnostics script lives in the project-root scripts/
directory, which is not mounted in the Docker dev container.  When
unavailable the tests are skipped.
"""

from __future__ import annotations

import datetime
import os
from unittest.mock import MagicMock

import pytest

# /app is the container working directory (project root).
_SCRIPTS_PATH = "/app/scripts/email_diagnostics.py"


def _skip_if_no_script():
    """Skip the current test if the diagnostics script is absent."""
    if not os.path.isfile(_SCRIPTS_PATH):
        pytest.skip(
            f"Diagnostics script not available at {_SCRIPTS_PATH} "
            "(scripts/ not mounted in dev container)"
        )


def _load_diagnostics():
    """Load the diagnostics module."""
    import importlib.util
    import sys

    _skip_if_no_script()
    spec = importlib.util.spec_from_file_location(
        "email_diagnostics", _SCRIPTS_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["email_diagnostics"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestReportAccount:
    """Tests for report_account()."""

    def test_returns_found_false_when_no_account(self):
        """report_account returns {found: False} for unknown user."""
        ed = _load_diagnostics()

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_session = MagicMock()
        mock_session.query.return_value = mock_query

        result = ed.report_account(mock_session, 999)
        assert result == {"found": False}

    def test_returns_account_fields_when_found(self):
        """report_account returns expected fields for a real account."""
        ed = _load_diagnostics()

        now = datetime.datetime(2026, 7, 20, 12, 0, 0)
        mock_acct = MagicMock()
        mock_acct.id = 42
        mock_acct.email_address = "test@example.com"
        mock_acct.provider = "fastmail"
        mock_acct.status = "connected"
        mock_acct.error_message = None
        mock_acct.last_synced_at = now
        mock_acct.backfill_completed_at = None

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_acct
        mock_session = MagicMock()
        mock_session.query.return_value = mock_query

        result = ed.report_account(mock_session, 1)
        assert result["found"] is True
        assert result["account_id"] == 42
        assert result["email"] == "test@example.com"
        assert result["status"] == "connected"
        assert "2026-07-20" in result["last_synced_at"]


class TestReportMessages:
    """Tests for report_messages()."""

    def test_returns_total_count(self):
        """report_messages returns total_messages from count."""
        ed = _load_diagnostics()

        mock_filter = MagicMock()
        mock_filter.filter.return_value = mock_filter
        mock_filter.count.return_value = 150
        mock_session = MagicMock()
        mock_session.query.return_value = mock_filter

        result = ed.report_messages(mock_session, 42)
        assert result["total_messages"] == 150
