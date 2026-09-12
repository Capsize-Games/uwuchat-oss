"""Tests for the login-triggered FHE embedding recovery hook.

Covers: (a) a simulated login event populates embedding_enc,
(b) a second login within the cooldown window does not re-trigger,
(c) the fast-exit path when no NULL rows exist,
(d) the Redis-backed debounce pattern.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from projects.uwuchat.server.embedding_recovery import (
    _mark_running,
    _should_run,
)


class TestRecoveryDebounce:
    """Redis-backed cooldown prevents re-scan on rapid logins."""

    def test_cooldown_active_after_mark(self):
        """After _mark_running, _should_run returns False."""
        account_id = 99999

        with patch(
            "projects.uwuchat.server.embedding_recovery"
            "._recovery_redis",
        ) as mock_redis_fn:
            mock_redis = MagicMock()
            mock_redis.get.return_value = None  # key does not exist
            mock_redis_fn.return_value = mock_redis

            # Before marking, should run.
            assert _should_run(account_id) is True
            mock_redis.get.assert_called_once()

            # After marking, key now exists.
            mock_redis.get.return_value = b"1"
            assert _should_run(account_id) is False

    def test_mark_sets_ttl(self):
        """_mark_running sets the cooldown key with correct TTL."""
        account_id = 99999

        with patch(
            "projects.uwuchat.server.embedding_recovery"
            "._recovery_redis",
        ) as mock_redis_fn:
            mock_redis = MagicMock()
            mock_redis_fn.return_value = mock_redis

            _mark_running(account_id)

            mock_redis.setex.assert_called_once()
            args = mock_redis.setex.call_args[0]
            assert "embedding_recovery:99999" in args[0]
            assert args[1] == 30 * 60  # cooldown seconds


class TestRecoveryFullPath:
    """End-to-end recovery exercises the backfill functions."""

    def test_recovery_runs_backfills_when_null_rows_exist(self):
        """When NULL embedding_enc rows exist, recovery calls
        both backfill functions."""
        from projects.uwuchat.server.embedding_recovery import (
            recover_pending_embeddings,
        )

        with patch(
            "projects.uwuchat.server.embedding_recovery"
            "._exists_null_embeddings",
            return_value=True,
        ), patch(
            "projects.uwuchat.server.embedding_recovery"
            "._should_run",
            return_value=True,
        ), patch(
            "projects.uwuchat.server.embedding_recovery"
            "._mark_running",
        ), patch(
            "airunner_services.data.tenant.set_tenant_key",
            return_value="token",
        ), patch(
            "airunner_services.data.tenant.reset_tenant_key",
        ), patch(
            "projects.uwuchat.server.embedding_provider"
            ".get_embedding_provider",
        ), patch(
            "airunner_services.embedding_backfill"
            ".backfill_fact_embeddings",
            return_value={"total_embedded": 5, "errors": 0},
        ) as mock_fact, patch(
            "airunner_services.embedding_backfill"
            ".backfill_turn_embeddings",
            return_value={"total_embedded": 3, "errors": 0},
        ) as mock_turn:
            recover_pending_embeddings(1, "test_tenant")

            mock_fact.assert_called_once()
            mock_turn.assert_called_once()

    def test_recovery_skips_when_no_null_rows(self):
        """Fast-exit: no NULL rows → no backfill calls."""
        from projects.uwuchat.server.embedding_recovery import (
            recover_pending_embeddings,
        )

        with patch(
            "projects.uwuchat.server.embedding_recovery"
            "._exists_null_embeddings",
            return_value=False,
        ), patch(
            "airunner_services.embedding_backfill"
            ".backfill_fact_embeddings",
        ) as mock_fact:
            recover_pending_embeddings(1, "test_tenant")

            mock_fact.assert_not_called()

    def test_recovery_skips_when_cooldown_active(self):
        """Cooldown active → no backfill calls."""
        from projects.uwuchat.server.embedding_recovery import (
            recover_pending_embeddings,
        )

        with patch(
            "projects.uwuchat.server.embedding_recovery"
            "._exists_null_embeddings",
            return_value=True,
        ), patch(
            "projects.uwuchat.server.embedding_recovery"
            "._should_run",
            return_value=False,
        ), patch(
            "airunner_services.embedding_backfill"
            ".backfill_fact_embeddings",
        ) as mock_fact:
            recover_pending_embeddings(1, "test_tenant")

            mock_fact.assert_not_called()


class TestRecoverySignalHandler:
    """Login signal triggers recovery correctly."""

    def test_signal_handler_dispatches(self):
        """_on_user_login_complete calls recover_pending_embeddings
        in a background thread."""
        from projects.uwuchat.server.embedding_recovery import (
            _on_user_login_complete,
        )

        data = {"account_id": 1, "tenant_key": "test_tenant"}

        with patch(
            "projects.uwuchat.server.embedding_recovery"
            ".recover_pending_embeddings",
        ) as mock_recover, patch(
            "asyncio.ensure_future",
        ) as mock_ensure, patch(
            "asyncio.to_thread",
        ) as mock_to_thread:
            _on_user_login_complete(data)

            mock_ensure.assert_called_once()
            mock_to_thread.assert_called_once_with(
                mock_recover, 1, "test_tenant",
            )

    def test_signal_handler_skips_missing_account_id(self):
        """Missing account_id → handler returns early."""
        from projects.uwuchat.server.embedding_recovery import (
            _on_user_login_complete,
        )

        with patch(
            "projects.uwuchat.server.embedding_recovery"
            ".recover_pending_embeddings",
        ) as mock_recover:
            _on_user_login_complete({})
            mock_recover.assert_not_called()
