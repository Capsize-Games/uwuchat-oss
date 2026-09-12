"""Verify email-sync cancellation is Redis-backed, not an in-process
set.

Context: ``cancel_sync()`` is called from ``_do_disconnect`` in the
API server process, while ``is_cancelled()`` is checked inside the
Celery sync tasks, which run in a separate worker process. An
in-process ``set`` (the original implementation) would never be seen
across that boundary — the disconnect-cancels-mid-sync guarantee
would silently stop working, exactly the same failure class as the
progress-bar bug (see ``sync_progress_store``).
"""

from __future__ import annotations

from unittest.mock import patch


class TestStartSync:
    def test_deletes_cancel_key(self) -> None:
        from projects.uwuchat.server.email.sync_cancellation import (
            start_sync,
        )

        with patch(
            "projects.uwuchat.server.email.sync_cancellation"
            ".cache_redis",
        ) as mock_redis:
            start_sync(7)
            mock_redis.return_value.delete.assert_called_once_with(
                "email_sync_cancel:7",
            )


class TestCancelSync:
    def test_sets_cancel_key_with_ttl(self) -> None:
        from projects.uwuchat.server.email.sync_cancellation import (
            _CANCEL_TTL_SECONDS,
            cancel_sync,
        )

        with patch(
            "projects.uwuchat.server.email.sync_cancellation"
            ".cache_redis",
        ) as mock_redis:
            cancel_sync(7)
            mock_redis.return_value.setex.assert_called_once_with(
                "email_sync_cancel:7", _CANCEL_TTL_SECONDS, "1",
            )


class TestIsCancelled:
    def test_true_when_key_exists(self) -> None:
        from projects.uwuchat.server.email.sync_cancellation import (
            is_cancelled,
        )

        with patch(
            "projects.uwuchat.server.email.sync_cancellation"
            ".cache_redis",
        ) as mock_redis:
            mock_redis.return_value.exists.return_value = 1
            assert is_cancelled(7) is True

    def test_false_when_key_missing(self) -> None:
        from projects.uwuchat.server.email.sync_cancellation import (
            is_cancelled,
        )

        with patch(
            "projects.uwuchat.server.email.sync_cancellation"
            ".cache_redis",
        ) as mock_redis:
            mock_redis.return_value.exists.return_value = 0
            assert is_cancelled(7) is False


class TestFinishSync:
    def test_deletes_cancel_key(self) -> None:
        from projects.uwuchat.server.email.sync_cancellation import (
            finish_sync,
        )

        with patch(
            "projects.uwuchat.server.email.sync_cancellation"
            ".cache_redis",
        ) as mock_redis:
            finish_sync(7)
            mock_redis.return_value.delete.assert_called_once_with(
                "email_sync_cancel:7",
            )
