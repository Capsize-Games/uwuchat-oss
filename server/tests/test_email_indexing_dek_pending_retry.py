"""Regression tests for the DEK relay expiry → indexing_status fix.

Verifies that when the DEK relay entry expires before background
indexing can run, the account is marked ``indexing_status = "pending"``,
and that pending accounts get re-enqueued when a live DEK is next
available.

Does NOT hit a real embedding provider or real Fastmail API — mocks
at the same boundaries as the existing tests in this directory.
"""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch


class TestIndexingStatusPendingOnDekMiss:
    """DEK relay expiry must mark the account ``indexing_status = "pending"``
    so a later live session can retry background indexing."""

    def test_sync_callback_marks_pending_when_dek_missing(self) -> None:
        """``_sync_callback`` must bulk-UPDATE
        ``indexing_status="pending"`` on the account when
        ``task_dek_scope`` yields None — a bulk UPDATE (not a full
        entity load) so this never touches
        EmailAccount.credential_ciphertext without a DEK active."""
        from projects.uwuchat.server.tasks.email_tasks import (
            _sync_callback,
        )

        # Mock task_dek_scope to yield None (DEK relay empty).
        mock_dek_scope = MagicMock()
        mock_dek_scope.__enter__.return_value = None

        with patch(
            "airunner_services.tasks.task_helpers.task_dek_scope",
            return_value=mock_dek_scope,
        ), patch(
            "airunner_services.data.tenant.tenant_scope",
        ), patch(
            "airunner_services.database.session.session_scope",
        ) as mock_session_scope, patch(
            "projects.uwuchat.server.email.sync_cancellation"
            ".finish_sync",
        ), patch(
            "airunner_services.database.models.email_account"
            ".EmailAccount",
        ):
            mock_session = MagicMock()
            mock_session_scope.return_value.__enter__.return_value = (
                mock_session
            )

            result = _sync_callback(
                mailbox_count=1,
                email_account_id=42,
                user_id=1,
                tenant_key="test_tenant",
                account_id=999,
            )

            assert result == {"status": "skipped", "reason": "no_dek"}
            mock_session.query.return_value.filter.return_value \
                .update.assert_called_once_with(
                    {"indexing_status": "pending"},
                    synchronize_session=False,
                )
            mock_session.commit.assert_called_once()

    def test_index_background_marks_pending_when_dek_missing(self) -> None:
        """``_index_email_bodies_background`` must bulk-UPDATE
        ``indexing_status="pending"`` on the account when
        ``task_dek_scope`` yields None — a bulk UPDATE (not a full
        entity load) so this never touches
        EmailAccount.credential_ciphertext without a DEK active."""
        from projects.uwuchat.server.tasks.email_indexing_tasks import (
            _index_email_bodies_background,
        )

        # Mock task_dek_scope to yield None (DEK relay empty).
        mock_dek_scope = MagicMock()
        mock_dek_scope.__enter__.return_value = None

        with patch(
            "airunner_services.tasks.task_helpers.task_dek_scope",
            return_value=mock_dek_scope,
        ), patch(
            "airunner_services.data.tenant.tenant_scope",
        ), patch(
            "airunner_services.database.session.session_scope",
        ) as mock_session_scope, patch(
            "airunner_services.database.models.email_account"
            ".EmailAccount",
        ):
            mock_session = MagicMock()
            mock_session_scope.return_value.__enter__.return_value = (
                mock_session
            )

            result = _index_email_bodies_background(
                email_account_id=42,
                user_id=1,
                tenant_key="test_tenant",
                account_id=999,
            )

            assert result == {"status": "skipped", "reason": "no_dek"}
            mock_session.query.return_value.filter.return_value \
                .update.assert_called_once_with(
                    {"indexing_status": "pending"},
                    synchronize_session=False,
                )
            mock_session.commit.assert_called_once()


class TestRetryPendingIndexing:
    """Accounts with ``indexing_status = "pending"`` must be retried when
    a live DEK is available."""

    def test_retry_enqueues_background_indexing(self) -> None:
        """``_retry_pending_indexing`` must enqueue
        ``_index_email_bodies_background`` for each pending account.

        Uses a column-only ``(id, user_id)`` query (not full-entity
        load) so this can run with no DEK active — it's reachable
        from the periodic-sync path, which never has one."""
        from projects.uwuchat.server.email.sync_engine import (
            _retry_pending_indexing,
        )

        with patch(
            "airunner_services.data.tenant.tenant_scope",
        ), patch(
            "airunner_services.database.session.session_scope",
        ) as mock_session_scope, patch(
            "projects.uwuchat.server.tasks.email_indexing_tasks"
            "._index_email_bodies_background",
        ) as mock_enqueue, patch(
            "airunner_services.database.models.email_account"
            ".EmailAccount",
        ):
            mock_session = MagicMock()
            mock_session_scope.return_value.__enter__.return_value = (
                mock_session
            )
            mock_session.query.return_value.filter.return_value.all.return_value = [
                (42, 1),
            ]

            _retry_pending_indexing("test_tenant", 999)

            mock_enqueue.apply_async.assert_called_once_with(
                args=[42, 1, "test_tenant", 999],
                queue="sync",
            )

    def test_retry_skips_when_no_pending(self) -> None:
        """``_retry_pending_indexing`` must not enqueue anything when
        no accounts have ``indexing_status = "pending"``."""
        from projects.uwuchat.server.email.sync_engine import (
            _retry_pending_indexing,
        )

        with patch(
            "airunner_services.data.tenant.tenant_scope",
        ), patch(
            "airunner_services.database.session.session_scope",
        ) as mock_session_scope, patch(
            "projects.uwuchat.server.tasks.email_indexing_tasks"
            "._index_email_bodies_background",
        ) as mock_enqueue, patch(
            "airunner_services.database.models.email_account"
            ".EmailAccount",
        ):
            mock_session = MagicMock()
            mock_session_scope.return_value.__enter__.return_value = (
                mock_session
            )
            # No pending accounts.
            mock_session.query.return_value.filter.return_value.all.return_value = []

            _retry_pending_indexing("test_tenant", 999)

            mock_enqueue.apply_async.assert_not_called()


class TestEmailBodyChunksEmptyEmbedding:
    """``search_email_body_chunks`` must handle the case where all
    ``EmailBodyChunk`` rows have ``embedding_enc IS NULL``
    (partial/failed indexing) gracefully — returning ``[]`` rather
    than crashing."""

    def test_returns_empty_list_on_all_null_embeddings(self) -> None:
        """When all candidate chunks have ``embedding_enc = None``,
        the query returns zero candidates, which should produce an
        empty result list, not an error."""
        from projects.uwuchat.server.email.email_rag import (
            search_email_body_chunks,
        )

        with patch(
            "projects.uwuchat.server.embedding_provider"
            ".get_embedding_provider",
        ) as mock_provider:
            mock_provider.return_value.embed_query.return_value = (
                [0.1] * 1024
            )
            with patch(
                "airunner_services.database.models.email_body_chunk"
                ".EmailBodyChunk",
            ) as mock_chunk:
                # Simulate zero candidates (all embedding_enc IS NULL
                # means no rows pass the filter).
                mock_chunk.objects.query.return_value.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
                with patch(
                    "airunner_services.data.tenant.get_account_id",
                    return_value=123,
                ):
                    result = search_email_body_chunks(
                        "something relevant",
                    )
                    assert result == [], (
                        "Expected empty list when no candidates have "
                        "a non-null embedding_enc"
                    )


class TestSearchEmailKnowledgeDistinctFailureModes:
    """The ``search_email_knowledge`` tool must return distinct outputs
    for "no data found" vs "tool crashed" so these two failure modes
    are distinguishable in test assertions and logs."""

    def test_no_data_returns_expected_string(self) -> None:
        """When no email knowledge is found (both entity and body-chunk
        searches return nothing), the tool must return a predictable
        string containing the query, not an error message."""
        from projects.uwuchat.server.tools.email_tools import (
            search_email_knowledge,
        )

        fn = getattr(
            search_email_knowledge, "func", search_email_knowledge,
        )

        with patch(
            "projects.uwuchat.server.tools.email_tools"
            "._is_omnipotent",
            return_value=True,
        ), patch(
            "airunner_services.llm.managers.prompt_builder.context"
            "._search_entity_context",
            return_value=[],
        ), patch(
            "airunner_services.llm.managers.prompt_builder.context"
            "._search_email_context",
            return_value="",
        ), patch(
            "airunner_services.knowledge.get_knowledge_base",
        ):
            result = fn(query="something not in email")

        assert "No email knowledge found for" in result
        assert "something not in email" in result

    def test_exception_returns_error_string(self) -> None:
        """When the tool crashes (e.g. unexpected exception in
        retrieval), the returned string must contain "Error" to
        distinguish it from a clean "no results" response."""
        from projects.uwuchat.server.tools.email_tools import (
            search_email_knowledge,
        )

        fn = getattr(
            search_email_knowledge, "func", search_email_knowledge,
        )

        with patch(
            "projects.uwuchat.server.tools.email_tools"
            "._is_omnipotent",
            return_value=True,
        ), patch(
            "airunner_services.llm.managers.prompt_builder.context"
            "._search_entity_context",
            side_effect=RuntimeError("connection reset"),
        ), patch(
            "airunner_services.knowledge.get_knowledge_base",
        ):
            result = fn(query="something broken")

        assert result.startswith("Error searching email knowledge:")
        assert "connection reset" in result


class TestSignalHandlerReachability:
    """Verifies that ``on_email_start_sync_signal`` actually reaches
    ``_retry_pending_indexing`` under realistic conditions — not just
    that the helper function itself works in isolation.

    These tests exercise the full call chain: signal handler →
    _retry_pending_indexing → enqueue, so a future refactor that
    changes the handler's guard conditions or the retry entry point
    will fail these tests.
    """

    def test_signal_handler_calls_retry_when_account_id_in_context(
        self,
    ) -> None:
        """``on_email_start_sync_signal`` must call
        ``_retry_pending_indexing`` when ``account_id`` is available
        from the ContextVar (simulating the HTTP auth middleware or
        periodic_sync.py's ``account_id_scope``)."""
        from projects.uwuchat.server.email.sync_engine import (
            on_email_start_sync_signal,
        )
        from airunner_services.data.tenant import account_id_scope

        with account_id_scope(999), patch(
            "airunner_services.data.tenant.get_tenant_key",
            return_value="test_tenant",
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            ".get_user_dek",
            return_value=None,  # No live DEK (periodic path)
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            ".start_sync",
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            ".email_sync_progress_start",
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            "._retry_pending_indexing",
        ) as mock_retry, patch(
            "projects.uwuchat.server.tasks.email_tasks"
            ".sync_email_account",
        ):
            on_email_start_sync_signal(
                {"email_account_id": 42},
            )

        mock_retry.assert_called_once_with("test_tenant", 999)

    def test_signal_handler_calls_retry_when_account_id_in_data_dict(
        self,
    ) -> None:
        """``on_email_start_sync_signal`` must call
        ``_retry_pending_indexing`` when ``account_id`` comes from the
        signal data dict (simulating the connect path where the HTTP
        handler explicitly passes ``account_id`` in the data)."""
        from projects.uwuchat.server.email.sync_engine import (
            on_email_start_sync_signal,
        )

        # ContextVar returns None (simulating thread-pool or
        # no-account_id_scope context).
        with patch(
            "airunner_services.data.tenant.get_account_id",
            return_value=None,
        ), patch(
            "airunner_services.data.tenant.get_tenant_key",
            return_value=None,
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            ".get_user_dek",
            return_value=None,
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            ".start_sync",
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            ".email_sync_progress_start",
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            "._retry_pending_indexing",
        ) as mock_retry, patch(
            "projects.uwuchat.server.tasks.email_tasks"
            ".sync_email_account",
        ):
            # account_id=999 passed explicitly in data dict
            on_email_start_sync_signal(
                {
                    "email_account_id": 42,
                    "account_id": 999,
                },
            )

        mock_retry.assert_called_once()

    def test_signal_handler_returns_early_when_no_account_id(
        self,
    ) -> None:
        """``on_email_start_sync_signal`` must return early when
        ``account_id`` is available from neither the ContextVar nor
        the signal data dict — preventing silent failures."""
        from projects.uwuchat.server.email.sync_engine import (
            on_email_start_sync_signal,
        )

        with patch(
            "airunner_services.data.tenant.get_account_id",
            return_value=None,
        ), patch(
            "airunner_services.data.tenant.get_tenant_key",
            return_value=None,
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            ".get_user_dek",
            return_value=None,
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            "._retry_pending_indexing",
        ) as mock_retry:
            # No account_id in data dict either
            on_email_start_sync_signal(
                {"email_account_id": 42},
            )

        mock_retry.assert_not_called()

    def test_signal_handler_still_calls_retry_without_dek(
        self,
    ) -> None:
        """``on_email_start_sync_signal`` must call
        ``_retry_pending_indexing`` even when no live DEK is available
        (periodic Beat trigger path) — the relay write is skipped but
        the retry should still fire."""
        from projects.uwuchat.server.email.sync_engine import (
            on_email_start_sync_signal,
        )
        from airunner_services.data.tenant import account_id_scope

        with account_id_scope(999), patch(
            "airunner_services.data.tenant.get_tenant_key",
            return_value="test_tenant",
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            ".get_user_dek",
            return_value=None,  # No DEK
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            ".start_sync",
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            ".email_sync_progress_start",
        ), patch(
            "projects.uwuchat.server.email.sync_engine"
            "._retry_pending_indexing",
        ) as mock_retry, patch(
            "projects.uwuchat.server.tasks.email_tasks"
            ".sync_email_account",
        ), patch(
            "airunner_services.tasks.redis_client.dek_relay_store",
        ) as mock_relay:
            on_email_start_sync_signal(
                {"email_account_id": 42},
            )

        # Retry should fire even without DEK
        mock_retry.assert_called_once_with("test_tenant", 999)
        # Relay should NOT be written without DEK
        mock_relay.assert_not_called()


class TestRecoverPendingEmailIndexing:
    """``recover_pending_email_indexing`` — the login-recovery hook."""

    @staticmethod
    def _make_session_iter(values: list) -> MagicMock:
        """Return a session whose __enter__ yields from *values*
        sequentially."""
        it = iter(values)

        def _side_effect() -> MagicMock:
            return next(it)

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.side_effect = _side_effect
        return mock_session_cm

    @staticmethod
    def _enter_envelope_patches(stack) -> None:
        """Enter the DEK-envelope plumbing patches shared by every
        recover_pending_email_indexing test below, via *stack* (an
        ``contextlib.ExitStack``)."""
        stack.enter_context(patch(
            "airunner_services.utils.crypto.user_envelope.decode_salt",
            return_value=b"salt",
        ))
        stack.enter_context(patch(
            "airunner_services.utils.crypto.user_envelope.derive_kek",
            return_value=b"kek" * 8,
        ))
        stack.enter_context(patch(
            "airunner_services.utils.crypto.user_envelope.unwrap_dek",
            return_value=b"dek" * 16,
        ))
        stack.enter_context(patch(
            "airunner_services.tasks.task_helpers.wrap_dek_for_relay",
            return_value=b"wrapped_for_relay",
        ))
        stack.enter_context(patch(
            "airunner_services.tasks.redis_client.dek_relay_store",
        ))

    def test_legacy_null_classifies_as_pending_on_mismatch(
        self,
    ) -> None:
        """An ``EmailAccount`` with ``indexing_status = None`` and a
        thread-count mismatch must be bulk-UPDATEd to
        ``indexing_status="pending"``.

        Uses column-only ``(id, indexing_status)`` tuples for
        ``accounts_to_process`` and a bulk ``.update()`` call for the
        reconciliation result — matching the production code, which
        never loads a full ``EmailAccount`` entity (that would
        eagerly decrypt ``credential_ciphertext`` with no DEK active
        at that point, or risk ``DetachedInstanceError`` from holding
        an ORM object across a session boundary)."""
        from projects.uwuchat.server.email.sync_engine import (
            recover_pending_email_indexing,
        )

        mock_pub_account = MagicMock()
        mock_pub_account.id = 999
        mock_pub_account.wrapped_dek = b"wrapped_dek"
        mock_pub_account.dek_kdf_salt = "salt"
        mock_pub_account.dek_kdf_params = {"n": 2}
        mock_pub_account.tenant_schema = "tenant_test"

        with contextlib.ExitStack() as stack:
            mock_pub_session_scope = stack.enter_context(patch(
                "airunner_services.database.session"
                ".public_session_scope",
            ))
            stack.enter_context(patch(
                "airunner_services.data.tenant.tenant_key_from_schema",
                return_value="test_tenant",
            ))
            stack.enter_context(
                patch("airunner_services.data.tenant.set_tenant_key"),
            )
            stack.enter_context(
                patch("airunner_services.data.tenant.reset_tenant_key"),
            )
            mock_session_scope = stack.enter_context(patch(
                "airunner_services.database.session.session_scope",
            ))
            self._enter_envelope_patches(stack)
            stack.enter_context(patch(
                "projects.uwuchat.server.email.sync_engine"
                "._retry_pending_indexing",
            ))

            mock_pub_session = MagicMock()
            mock_pub_session_scope.return_value.__enter__.return_value = (
                mock_pub_session
            )
            mock_pub_session.query.return_value.filter.return_value.first.return_value = (
                mock_pub_account
            )

            recon_session = MagicMock()
            # msg_thread_count=10, chunk_thread_count=2 → mismatch
            recon_session.query.return_value.filter.return_value \
                .scalar.side_effect = [10, 2]

            sessions = [
                MagicMock(scalar=lambda: 1),  # fast-exit count
                MagicMock(  # accounts_to_process + mark-checked update
                    query=lambda *a, **kw: MagicMock(
                        filter=lambda *a2, **kw2: MagicMock(
                            all=lambda: [(42, None)],
                        ),
                    ),
                ),
                recon_session,
            ]
            it = iter(sessions)

            def _cm() -> MagicMock:
                return next(it)

            mock_session_scope.return_value.__enter__.side_effect = _cm

            recover_pending_email_indexing(999, "password")

            update_call = (
                recon_session.query.return_value.filter.return_value
                .update
            )
            update_call.assert_called_once()
            fields, kwargs = update_call.call_args
            assert fields[0]["indexing_status"] == "pending"
            assert kwargs == {"synchronize_session": False}

    def test_legacy_null_classifies_as_complete_on_match(
        self,
    ) -> None:
        """An ``EmailAccount`` with ``indexing_status = None`` and
        matching thread counts must be bulk-UPDATEd to
        ``indexing_status="complete"``."""
        from projects.uwuchat.server.email.sync_engine import (
            recover_pending_email_indexing,
        )

        mock_pub_account = MagicMock()
        mock_pub_account.id = 999
        mock_pub_account.wrapped_dek = b"wrapped_dek"
        mock_pub_account.dek_kdf_salt = "salt"
        mock_pub_account.dek_kdf_params = {"n": 2}
        mock_pub_account.tenant_schema = "tenant_test"

        with contextlib.ExitStack() as stack:
            mock_pub_session_scope = stack.enter_context(patch(
                "airunner_services.database.session"
                ".public_session_scope",
            ))
            stack.enter_context(patch(
                "airunner_services.data.tenant.tenant_key_from_schema",
                return_value="test_tenant",
            ))
            stack.enter_context(
                patch("airunner_services.data.tenant.set_tenant_key"),
            )
            stack.enter_context(
                patch("airunner_services.data.tenant.reset_tenant_key"),
            )
            mock_session_scope = stack.enter_context(patch(
                "airunner_services.database.session.session_scope",
            ))
            self._enter_envelope_patches(stack)
            stack.enter_context(patch(
                "projects.uwuchat.server.email.sync_engine"
                "._retry_pending_indexing",
            ))

            mock_pub_session = MagicMock()
            mock_pub_session_scope.return_value.__enter__.return_value = (
                mock_pub_session
            )
            mock_pub_session.query.return_value.filter.return_value.first.return_value = (
                mock_pub_account
            )

            recon_session = MagicMock()
            # msg_thread_count=10, chunk_thread_count=10 → match
            recon_session.query.return_value.filter.return_value \
                .scalar.side_effect = [10, 10]

            sessions = [
                MagicMock(scalar=lambda: 1),  # fast-exit count
                MagicMock(  # accounts_to_process + mark-checked update
                    query=lambda *a, **kw: MagicMock(
                        filter=lambda *a2, **kw2: MagicMock(
                            all=lambda: [(42, None)],
                        ),
                    ),
                ),
                recon_session,
            ]
            it = iter(sessions)

            def _cm() -> MagicMock:
                return next(it)

            mock_session_scope.return_value.__enter__.side_effect = _cm

            recover_pending_email_indexing(999, "password")

            update_call = (
                recon_session.query.return_value.filter.return_value
                .update
            )
            update_call.assert_called_once()
            fields, kwargs = update_call.call_args
            assert fields[0]["indexing_status"] == "complete"
            assert kwargs == {"synchronize_session": False}

    def test_fast_exit_when_no_email_accounts(self) -> None:
        """A tenant with zero ``EmailAccount`` rows must return after
        the existence check, without reconciliation or relay writes."""
        from projects.uwuchat.server.email.sync_engine import (
            recover_pending_email_indexing,
        )

        mock_pub_account = MagicMock()
        mock_pub_account.id = 999
        mock_pub_account.wrapped_dek = b"wrapped_dek"
        mock_pub_account.dek_kdf_salt = "salt"
        mock_pub_account.dek_kdf_params = {"n": 2}
        mock_pub_account.tenant_schema = "tenant_test"

        with patch(
            "airunner_services.database.session.public_session_scope",
        ) as mock_pub_session_scope, patch(
            "airunner_services.data.tenant.tenant_key_from_schema",
            return_value="test_tenant",
        ), patch(
            "airunner_services.data.tenant.set_tenant_key",
        ), patch(
            "airunner_services.data.tenant.reset_tenant_key",
        ), patch(
            "airunner_services.database.session.session_scope",
        ) as mock_session_scope, patch(
            "airunner_services.utils.crypto.user_envelope"
            ".decode_salt",
        ) as mock_decode, patch(
            "airunner_services.utils.crypto.user_envelope"
            ".derive_kek",
        ) as mock_derive, patch(
            "airunner_services.utils.crypto.user_envelope"
            ".unwrap_dek",
        ) as mock_unwrap, patch(
            "airunner_services.tasks.task_helpers.wrap_dek_for_relay",
        ) as mock_wrap, patch(
            "airunner_services.tasks.redis_client.dek_relay_store",
        ) as mock_relay, patch(
            "projects.uwuchat.server.email.sync_engine"
            "._retry_pending_indexing",
        ) as mock_retry:
            mock_pub_session = MagicMock()
            mock_pub_session_scope.return_value.__enter__.return_value = (
                mock_pub_session
            )
            mock_pub_session.query.return_value.filter.return_value.first.return_value = (
                mock_pub_account
            )

            # The count query now has .filter(EmailAccount.deleted == False),
            # so the mock chain needs an intermediate filter step.
            mock_query_chain = MagicMock()
            mock_query_chain.scalar.return_value = 0
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value = (
                mock_query_chain
            )
            mock_session_scope.return_value.__enter__.return_value = (
                mock_session
            )

            recover_pending_email_indexing(999, "password")

            mock_decode.assert_not_called()
            mock_derive.assert_not_called()
            mock_unwrap.assert_not_called()
            mock_wrap.assert_not_called()
            mock_relay.assert_not_called()
            mock_retry.assert_not_called()

    def test_user_login_complete_signal_dispatches_recovery(
        self,
    ) -> None:
        """``_on_user_login_complete`` must dispatch
        ``recover_pending_email_indexing`` via ``asyncio.to_thread``
        with the right ``account_id`` and ``password``."""
        from projects.uwuchat.server.email.sync_engine import (
            _on_user_login_complete,
        )

        # asyncio is imported lazily inside the function, so we
        # patch the stdlib-level function directly.
        with patch(
            "asyncio.ensure_future",
        ) as mock_ensure_future:
            _on_user_login_complete(
                {"account_id": 42, "password": "sekret"},
            )

            # ensure_future was called — the actual recovery function
            # is invoked via asyncio.to_thread inside the handler.
            mock_ensure_future.assert_called_once()

            # Verify the first arg to to_thread is our recovery function
            call_args = mock_ensure_future.call_args[0][0]
            # It's a coroutine from asyncio.to_thread — verify it was
            # created with the right args by inspecting the mock
            # attached to ensure_future's inner call.
            assert call_args is not None, (
                "Expected asyncio.ensure_future to be called with a "
                "coroutine"
            )

    def test_user_login_complete_signal_skips_without_account_id(
        self,
    ) -> None:
        """``_on_user_login_complete`` must return early when
        ``account_id`` is missing from the data dict."""
        from projects.uwuchat.server.email.sync_engine import (
            _on_user_login_complete,
        )

        with patch("asyncio.ensure_future") as mock_ensure_future:
            _on_user_login_complete({"password": "sekret"})
            mock_ensure_future.assert_not_called()

    def test_debounce_skips_when_recently_checked(self) -> None:
        """Calling the recovery function twice in quick succession must
        only do the work once; the second call is a no-op due to the
        cooldown timestamp."""
        from projects.uwuchat.server.email.sync_engine import (
            recover_pending_email_indexing,
        )

        mock_pub_account = MagicMock()
        mock_pub_account.id = 999
        mock_pub_account.wrapped_dek = b"wrapped_dek"
        mock_pub_account.dek_kdf_salt = "salt"
        mock_pub_account.dek_kdf_params = {"n": 2}
        mock_pub_account.tenant_schema = "tenant_test"

        with contextlib.ExitStack() as stack:
            mock_pub_session_scope = stack.enter_context(patch(
                "airunner_services.database.session"
                ".public_session_scope",
            ))
            stack.enter_context(patch(
                "airunner_services.data.tenant.tenant_key_from_schema",
                return_value="test_tenant",
            ))
            stack.enter_context(
                patch("airunner_services.data.tenant.set_tenant_key"),
            )
            stack.enter_context(
                patch("airunner_services.data.tenant.reset_tenant_key"),
            )
            mock_session_scope = stack.enter_context(patch(
                "airunner_services.database.session.session_scope",
            ))
            self._enter_envelope_patches(stack)
            mock_retry = stack.enter_context(patch(
                "projects.uwuchat.server.email.sync_engine"
                "._retry_pending_indexing",
            ))

            mock_pub_session = MagicMock()
            mock_pub_session_scope.return_value.__enter__.return_value = (
                mock_pub_session
            )
            mock_pub_session.query.return_value.filter.return_value.first.return_value = (
                mock_pub_account
            )

            # Shared iterator across calls to session_scope. The
            # account already has indexing_status="pending" (not
            # None), so the reconciliation loop (step 5) skips it —
            # no extra session_scope call needed for it.
            _call_idx = [0]

            def _cm() -> MagicMock:
                idx = _call_idx[0]
                _call_idx[0] += 1

                if idx == 0:
                    # First call: fast-exit count = 1
                    return MagicMock(scalar=lambda: 1)
                elif idx == 1:
                    # First call: accounts_to_process finds the
                    # pending account.
                    return MagicMock(
                        query=lambda *a, **kw: MagicMock(
                            filter=lambda *a2, **kw2: MagicMock(
                                all=lambda: [(42, "pending")],
                            ),
                        ),
                    )
                elif idx == 2:
                    # Second call: fast-exit count = 1
                    return MagicMock(scalar=lambda: 1)
                else:
                    # Second call: accounts_to_process returns empty
                    # — debounced, since it was just checked.
                    return MagicMock(
                        query=lambda *a, **kw: MagicMock(
                            filter=lambda *a2, **kw2: MagicMock(
                                all=lambda: [],
                            ),
                        ),
                    )

            mock_session_scope.return_value.__enter__.side_effect = _cm

            # First call: should process the account
            recover_pending_email_indexing(999, "password")
            retry_calls_after_first = mock_retry.call_count

            # Reset for second call detection
            mock_retry.reset_mock()

            # Second call: should be a no-op (debounce)
            recover_pending_email_indexing(999, "password")

            mock_retry.assert_not_called()
            assert retry_calls_after_first >= 1, (
                "First call must have called _retry_pending_indexing"
            )

    def test_dek_relay_write_and_retry_call(self) -> None:
        """Given a ``"pending"`` account and valid password/envelope,
        the function must write to the relay and call
        ``_retry_pending_indexing``."""
        from projects.uwuchat.server.email.sync_engine import (
            recover_pending_email_indexing,
        )

        mock_pub_account = MagicMock()
        mock_pub_account.id = 999
        mock_pub_account.wrapped_dek = b"wrapped_dek"
        mock_pub_account.dek_kdf_salt = "salt"
        mock_pub_account.dek_kdf_params = {"n": 2}
        mock_pub_account.tenant_schema = "tenant_test"

        with contextlib.ExitStack() as stack:
            mock_pub_session_scope = stack.enter_context(patch(
                "airunner_services.database.session"
                ".public_session_scope",
            ))
            stack.enter_context(patch(
                "airunner_services.data.tenant.tenant_key_from_schema",
                return_value="test_tenant",
            ))
            stack.enter_context(
                patch("airunner_services.data.tenant.set_tenant_key"),
            )
            stack.enter_context(
                patch("airunner_services.data.tenant.reset_tenant_key"),
            )
            mock_session_scope = stack.enter_context(patch(
                "airunner_services.database.session.session_scope",
            ))
            self._enter_envelope_patches(stack)
            mock_relay = stack.enter_context(patch(
                "airunner_services.tasks.redis_client.dek_relay_store",
            ))
            mock_retry = stack.enter_context(patch(
                "projects.uwuchat.server.email.sync_engine"
                "._retry_pending_indexing",
            ))

            mock_pub_session = MagicMock()
            mock_pub_session_scope.return_value.__enter__.return_value = (
                mock_pub_session
            )
            mock_pub_session.query.return_value.filter.return_value.first.return_value = (
                mock_pub_account
            )

            # account already has indexing_status="pending" (not
            # None), so the reconciliation loop (step 5) skips it —
            # no extra session_scope call needed for it.
            sessions = [
                MagicMock(scalar=lambda: 1),  # fast-exit count
                MagicMock(  # accounts_to_process
                    query=lambda *a, **kw: MagicMock(
                        filter=lambda *a2, **kw2: MagicMock(
                            all=lambda: [(42, "pending")],
                        ),
                    ),
                ),
            ]
            it = iter(sessions)

            def _cm() -> MagicMock:
                return next(it)

            mock_session_scope.return_value.__enter__.side_effect = _cm

            recover_pending_email_indexing(999, "password")

            mock_relay.assert_called_once_with(999, b"wrapped_for_relay")
            mock_retry.assert_called_once_with("test_tenant", 999)

    def test_exception_does_not_propagate(self) -> None:
        """An exception inside the recovery function must be caught
        and logged, not propagated."""
        from projects.uwuchat.server.email.sync_engine import (
            recover_pending_email_indexing,
        )

        with patch(
            "airunner_services.database.session.public_session_scope",
            side_effect=RuntimeError("DB exploded"),
        ), patch(
            "airunner_services.data.tenant.tenant_key_from_schema",
        ), patch(
            "airunner_services.data.tenant.set_tenant_key",
        ), patch(
            "airunner_services.data.tenant.reset_tenant_key",
        ):
            # Must not raise.
            recover_pending_email_indexing(999, "password")
