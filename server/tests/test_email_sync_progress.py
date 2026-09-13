"""Verify the account-scoped, cross-process email-sync progress store
and the ``_do_sync_progress``/RPC auth path built on top of it.

Context: email sync runs as Celery tasks in a worker process separate
from the API server, so progress can no longer be pushed over the
in-process ``WsEventBus`` (see ``sync_progress_events.py``). The whole
account's sync is a *single* progress bar, not one per mailbox — with
30+ mailboxes on a real account, one bar each was an unreadable wall
of bars. Backfill (concurrent, one Celery task per mailbox) reports
via an atomic HINCRBY delta; sequential phases (contacts,
summarization) set an absolute current/total instead.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestEmailSyncProgressStart:
    """``email_sync_progress_start`` resets stale state from a prior run."""

    def test_deletes_then_seeds_active_hash(self) -> None:
        from projects.uwuchat.server.email.sync_progress_store import (
            email_sync_progress_start,
        )

        with patch(
            "projects.uwuchat.server.email.sync_progress_store"
            ".cache_redis",
        ) as mock_redis:
            mock_pipe = mock_redis.return_value.pipeline.return_value
            email_sync_progress_start(7)

            mock_pipe.delete.assert_called_once_with("email_sync:7")
            mapping = mock_pipe.hset.call_args.kwargs["mapping"]
            assert mapping["active"] == "1"
            assert mapping["current"] == "0"
            assert mapping["success"] == ""


class TestEmailSyncProgressSetTotal:
    """``email_sync_progress_set_total`` seeds the denominator upfront."""

    def test_sets_total_and_label(self) -> None:
        from projects.uwuchat.server.email.sync_progress_store import (
            email_sync_progress_set_total,
        )

        with patch(
            "projects.uwuchat.server.email.sync_progress_store"
            ".cache_redis",
        ) as mock_redis:
            mock_pipe = mock_redis.return_value.pipeline.return_value
            email_sync_progress_set_total(7, 4957, "Starting sync…")

            mapping = mock_pipe.hset.call_args.kwargs["mapping"]
            assert mapping["total"] == "4957"
            assert mapping["label"] == "Starting sync…"


class TestEmailSyncProgressIncrement:
    """``email_sync_progress_increment`` atomically bumps the counter."""

    def test_uses_hincrby_not_read_modify_write(self) -> None:
        """Concurrent mailbox tasks must not lose updates to a race —
        HINCRBY, not GET-then-SET, is what makes that safe."""
        from projects.uwuchat.server.email.sync_progress_store import (
            email_sync_progress_increment,
        )

        with patch(
            "projects.uwuchat.server.email.sync_progress_store"
            ".cache_redis",
        ) as mock_redis:
            mock_pipe = mock_redis.return_value.pipeline.return_value
            email_sync_progress_increment(7, 50, "Syncing Inbox")

            mock_pipe.hincrby.assert_called_once_with(
                "email_sync:7", "current", 50,
            )
            mapping = mock_pipe.hset.call_args.kwargs["mapping"]
            assert mapping["label"] == "Syncing Inbox"
            assert mapping["active"] == "1"


class TestEmailSyncProgressWrite:
    """``email_sync_progress_write`` sets an absolute current/total —
    for sequential (non-concurrent) phases like summarization."""

    def test_sets_current_and_total_directly(self) -> None:
        from projects.uwuchat.server.email.sync_progress_store import (
            email_sync_progress_write,
        )

        with patch(
            "projects.uwuchat.server.email.sync_progress_store"
            ".cache_redis",
        ) as mock_redis:
            mock_pipe = mock_redis.return_value.pipeline.return_value
            email_sync_progress_write(
                7, "Processing messages", 10, 40,
            )

            mapping = mock_pipe.hset.call_args.kwargs["mapping"]
            assert mapping["current"] == "10"
            assert mapping["total"] == "40"
            assert mapping["label"] == "Processing messages"


class TestEmailSyncCompleteWrite:
    """``email_sync_complete_write`` sets the terminal state."""

    def test_sets_success_and_message(self) -> None:
        from projects.uwuchat.server.email.sync_progress_store import (
            EMAIL_SYNC_COMPLETE_TTL_SECONDS,
            email_sync_complete_write,
        )

        with patch(
            "projects.uwuchat.server.email.sync_progress_store"
            ".cache_redis",
        ) as mock_redis:
            mock_pipe = mock_redis.return_value.pipeline.return_value

            email_sync_complete_write(7, True, "Email sync complete")

            mapping = mock_pipe.hset.call_args.kwargs["mapping"]
            assert mapping["active"] == "0"
            assert mapping["success"] == "1"
            assert mapping["message"] == "Email sync complete"
            mock_pipe.expire.assert_called_once_with(
                "email_sync:7", EMAIL_SYNC_COMPLETE_TTL_SECONDS,
            )


class TestEmailSyncProgressRead:
    """``email_sync_progress_read`` computes percentage at read time,
    from whatever current/total are currently stored."""

    def test_returns_idle_shape_when_hash_missing(self) -> None:
        from projects.uwuchat.server.email.sync_progress_store import (
            email_sync_progress_read,
        )

        with patch(
            "projects.uwuchat.server.email.sync_progress_store"
            ".cache_redis",
        ) as mock_redis:
            mock_redis.return_value.hgetall.return_value = {}
            result = email_sync_progress_read(7)

        assert result == {
            "active": False, "current": 0, "total": 0, "progress": 0,
            "label": "", "unit": "messages",
            "success": None, "message": "",
        }

    def test_computes_percentage_from_current_and_total(self) -> None:
        from projects.uwuchat.server.email.sync_progress_store import (
            email_sync_progress_read,
        )

        with patch(
            "projects.uwuchat.server.email.sync_progress_store"
            ".cache_redis",
        ) as mock_redis:
            mock_redis.return_value.hgetall.return_value = {
                "active": "1",
                "current": "1300",
                "total": "4957",
                "label": "Syncing Inbox",
                "unit": "messages",
                "success": "",
                "message": "",
            }
            result = email_sync_progress_read(7)

        assert result["active"] is True
        assert result["current"] == 1300
        assert result["total"] == 4957
        assert result["progress"] == 26
        assert result["success"] is None

    def test_zero_total_produces_zero_percent_not_a_crash(self) -> None:
        from projects.uwuchat.server.email.sync_progress_store import (
            email_sync_progress_read,
        )

        with patch(
            "projects.uwuchat.server.email.sync_progress_store"
            ".cache_redis",
        ) as mock_redis:
            mock_redis.return_value.hgetall.return_value = {
                "active": "1", "current": "0", "total": "0",
                "label": "Starting sync…", "unit": "messages",
                "success": "", "message": "",
            }
            result = email_sync_progress_read(7)

        assert result["progress"] == 0

    def test_parses_success_false_on_completion(self) -> None:
        from projects.uwuchat.server.email.sync_progress_store import (
            email_sync_progress_read,
        )

        with patch(
            "projects.uwuchat.server.email.sync_progress_store"
            ".cache_redis",
        ) as mock_redis:
            mock_redis.return_value.hgetall.return_value = {
                "active": "0",
                "current": "0",
                "total": "0",
                "success": "0",
                "message": "No credential stored",
            }
            result = email_sync_progress_read(7)

        assert result["active"] is False
        assert result["success"] is False


class TestDoSyncProgress:
    """``_do_sync_progress`` resolves user_id -> account_id, then reads."""

    def test_idle_shape_when_no_account(self) -> None:
        """_do_sync_progress runs a column-only query for just the
        account id — not a full entity — so the no-match case is a
        scalar None, not a .first() None."""
        from projects.uwuchat.server.email.routes import _do_sync_progress

        with patch(
            "projects.uwuchat.server.email.routes.session_scope",
        ) as mock_scope:
            mock_session = MagicMock()
            mock_scope.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.filter.return_value.scalar.return_value = None

            result = _do_sync_progress(42)

        assert result == {
            "active": False, "current": 0, "total": 0, "progress": 0,
            "label": "", "unit": "messages",
            "success": None, "message": "",
        }

    def test_reads_progress_for_resolved_account(self) -> None:
        """Column-only query: .scalar() returns the plain account id,
        not a loaded EmailAccount entity."""
        from projects.uwuchat.server.email.routes import _do_sync_progress

        with patch(
            "projects.uwuchat.server.email.routes.session_scope",
        ) as mock_scope:
            mock_session = MagicMock()
            mock_scope.return_value.__enter__.return_value = mock_session
            mock_session.query.return_value.filter.return_value.scalar.return_value = 99

            with patch(
                "projects.uwuchat.server.email.sync_progress_store"
                ".email_sync_progress_read",
                return_value={"active": True, "current": 5, "total": 10},
            ) as mock_read:
                result = _do_sync_progress(42)

            mock_read.assert_called_once_with(99)

        assert result == {"active": True, "current": 5, "total": 10}
