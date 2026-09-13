"""Tests for email sync-status endpoint (Part 3).

Verifies last_synced_at is returned accurately and the sync-progress
read function returns the correct shape from Redis.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

from projects.uwuchat.server.email.routes import _do_status


def test_email_status_includes_last_synced_at():
    """_do_status returns last_synced_at ISO string when account exists."""
    now = datetime.datetime(2026, 7, 20, 12, 0, 0)
    # _do_status runs a column-only query (status, email_address,
    # provider, last_synced_at, error_message) — not a full entity —
    # so .first() returns a plain tuple/Row, not an EmailAccount.
    row = ("connected", "test@example.com", "fastmail", now, None)

    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = row

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value = mock_query

    with patch(
        "projects.uwuchat.server.email.routes.session_scope",
        return_value=mock_session,
    ):
        result = _do_status(1)

    assert result["connected"] is True
    assert result["last_synced_at"] == "2026-07-20T12:00:00"


def test_email_status_returns_none_for_unconnected():
    """_do_status returns not_connected and None last_synced_at."""
    mock_query = MagicMock()
    mock_query.filter.return_value = mock_query
    mock_query.first.return_value = None

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.query.return_value = mock_query

    with patch(
        "projects.uwuchat.server.email.routes.session_scope",
        return_value=mock_session,
    ):
        result = _do_status(1)

    assert result["connected"] is False
    assert result["last_synced_at"] is None


def test_sync_progress_read_returns_progress_shape():
    """email_sync_progress_read returns the correct dict shape."""
    from projects.uwuchat.server.email.sync_progress_store import (
        email_sync_progress_read,
    )
    from unittest.mock import patch as mock_patch

    mock_redis = MagicMock()
    mock_redis.hgetall.return_value = {
        "active": "1",
        "current": "500",
        "total": "1000",
        "label": "Background indexing",
        "unit": "threads",
        "success": "1",
        "message": "",
    }

    with mock_patch(
        "projects.uwuchat.server.email.sync_progress_store.cache_redis",
        return_value=mock_redis,
    ):
        result = email_sync_progress_read(42)

    assert result["active"] is True
    assert result["current"] == 500
    assert result["total"] == 1000
    assert result["progress"] == 50
    assert result["unit"] == "threads"
    assert result["label"] == "Background indexing"
    assert result["success"] is True


def test_sync_progress_read_returns_idle_when_empty():
    """email_sync_progress_read returns idle shape for missing key."""
    from projects.uwuchat.server.email.sync_progress_store import (
        email_sync_progress_read,
    )
    from unittest.mock import patch as mock_patch

    mock_redis = MagicMock()
    mock_redis.hgetall.return_value = {}

    with mock_patch(
        "projects.uwuchat.server.email.sync_progress_store.cache_redis",
        return_value=mock_redis,
    ):
        result = email_sync_progress_read(42)

    assert result["active"] is False
    assert result["progress"] == 0
