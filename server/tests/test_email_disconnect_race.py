"""Regression: disconnect races with in-flight sync's completion.

Part 4 — ``_sync_callback`` must re-check the account's
``deleted``/cancellation state before marking it "connected". A
disconnect that happens while the sync task is running must NOT
resurrect the account as "connected".
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet


class TestSyncCallbackSkipsDeletedAccount:
    """``_sync_callback`` must not mark an account "connected" if it
    was deleted (disconnected) while the sync was running."""

    def _make_mock_session(self, acct_deleted: bool) -> MagicMock:
        """Build a mock DB session whose ``get()`` returns an
        EmailAccount with the given ``deleted`` flag."""
        mock_account = MagicMock()
        mock_account.deleted = acct_deleted
        mock_account.credential_ciphertext = "fake-encrypted-token"
        mock_account.id = 1

        mock_session = MagicMock()
        mock_session.query.return_value.get.return_value = mock_account
        return mock_session

    def _make_multisession_cm(
        self, sessions: list[MagicMock],
    ) -> MagicMock:
        """Return a context-manager mock that returns each session
        in order on nested ``with session_scope()`` calls."""
        mock_cm = MagicMock()
        mock_cm.__enter__.side_effect = sessions
        mock_cm.__exit__.return_value = None
        return mock_cm

    def test_skips_completion_when_account_deleted(self) -> None:
        """When the account's ``deleted`` flag flips between the
        credential-load query and the completion-block query, the
        callback must abort without marking "connected"."""
        dek = Fernet.generate_key()

        first_session = self._make_mock_session(acct_deleted=False)
        second_session = self._make_mock_session(acct_deleted=True)

        mock_session_scope_cm = self._make_multisession_cm(
            [first_session, second_session],
        )

        with patch(
            "airunner_services.tasks.task_helpers.task_dek_scope",
        ) as mock_dek_scope:
            mock_dek_scope.return_value.__enter__.return_value = dek
            mock_dek_scope.return_value.__exit__.return_value = None

            with patch(
                "airunner_services.data.tenant.tenant_scope",
            ), patch(
                "airunner_services.database.session.session_scope",
                return_value=mock_session_scope_cm,
            ), patch(
                "projects.uwuchat.server.email.sync_cancellation"
                ".finish_sync",
            ), patch(
                "projects.uwuchat.server.email.sync_cancellation"
                ".is_cancelled",
                return_value=False,
            ), patch(
                "projects.uwuchat.server.email.sync_delta"
                ".delta_sync_account",
            ), patch(
                "projects.uwuchat.server.email.sync_pipeline"
                ".process_new_messages",
            ), patch(
                "projects.uwuchat.server.email.stats"
                ".compute_email_stats",
            ), patch(
                "projects.uwuchat.server.email.fastmail"
                ".FastmailJMAPProvider",
            ), patch(
                "projects.uwuchat.server.tasks.email_tasks._run_async",
                return_value=[],
            ), patch(
                "projects.uwuchat.server.email.sync_progress_events"
                ".emit_complete",
            ), patch(
                "projects.uwuchat.server.tasks"
                ".email_indexing_tasks._index_email_bodies_background",
            ):
                from projects.uwuchat.server.tasks.email_tasks import (
                    _sync_callback,
                )

                # _sync_callback is decorated with @app.task(bind=True),
                # so Celery's Task.__call__ auto-injects the task instance
                # as self.  Do NOT pass None for self.
                result = _sync_callback(
                    1,     # mailbox_count
                    1,     # email_account_id
                    1,     # user_id
                    "tenant_key",
                    1,     # account_id
                )

                assert result["status"] == "cancelled"
                assert (
                    result["reason"]
                    == "account_deleted_during_sync"
                )

    def test_skips_completion_when_cancelled(self) -> None:
        """When ``is_cancelled`` returns True during the completion
        block, the callback must abort without marking "connected"."""
        dek = Fernet.generate_key()

        first_session = self._make_mock_session(acct_deleted=False)
        second_session = self._make_mock_session(acct_deleted=False)

        mock_session_scope_cm = self._make_multisession_cm(
            [first_session, second_session],
        )

        with patch(
            "airunner_services.tasks.task_helpers.task_dek_scope",
        ) as mock_dek_scope:
            mock_dek_scope.return_value.__enter__.return_value = dek
            mock_dek_scope.return_value.__exit__.return_value = None

            with patch(
                "airunner_services.data.tenant.tenant_scope",
            ), patch(
                "airunner_services.database.session.session_scope",
                return_value=mock_session_scope_cm,
            ), patch(
                "projects.uwuchat.server.email.sync_cancellation"
                ".finish_sync",
            ), patch(
                "projects.uwuchat.server.email.sync_cancellation"
                ".is_cancelled",
                return_value=True,
            ), patch(
                "projects.uwuchat.server.email.sync_delta"
                ".delta_sync_account",
            ), patch(
                "projects.uwuchat.server.email.sync_pipeline"
                ".process_new_messages",
            ), patch(
                "projects.uwuchat.server.email.stats"
                ".compute_email_stats",
            ), patch(
                "projects.uwuchat.server.email.fastmail"
                ".FastmailJMAPProvider",
            ), patch(
                "projects.uwuchat.server.tasks.email_tasks._run_async",
                return_value=[],
            ), patch(
                "projects.uwuchat.server.email.sync_progress_events"
                ".emit_complete",
            ), patch(
                "projects.uwuchat.server.tasks"
                ".email_indexing_tasks._index_email_bodies_background",
            ):
                from projects.uwuchat.server.tasks.email_tasks import (
                    _sync_callback,
                )

                result = _sync_callback(
                    1,     # mailbox_count
                    1,     # email_account_id
                    1,     # user_id
                    "tenant_key",
                    1,     # account_id
                )

                assert result["status"] == "cancelled"
                assert (
                    result["reason"]
                    == "sync_cancelled_during_sync"
                )
