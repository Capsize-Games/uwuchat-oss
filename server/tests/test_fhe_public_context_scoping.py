"""FHE public-context resolver and EmailAccount ID scoping tests.

Covers shared ``get_or_create_public_context`` and the regression guard
against using mailbox row ID instead of platform account ID.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)


# ── Shared public-context resolver ───────────────────────────────


class TestGetOrCreatePublicContext:
    """The shared function replaces the knowledge_crud copy."""

    def test_importable_from_shared_location(self) -> None:
        from airunner_services.utils.crypto.fhe_account_context import (
            get_or_create_public_context,
        )
        assert callable(get_or_create_public_context)

    def test_raises_without_dek_on_creation(self) -> None:
        from airunner_services.utils.crypto.fhe_account_context import (
            get_or_create_public_context,
        )

        with patch(
            "airunner_services.database.models.fhe_key_material"
            ".FheKeyMaterial",
        ) as mock_fkm, patch(
            "airunner_services.utils.crypto.dek_cache.get_user_dek",
            return_value=None,
        ):
            mock_tx_ctx = MagicMock()
            mock_fkm.objects.transaction.return_value.__enter__.return_value = mock_tx_ctx
            mock_tx_ctx.query.return_value.filter.return_value.first.return_value = None

            with pytest.raises(DataEncryptionError):
                get_or_create_public_context(1)

    def test_re_export_from_knowledge_crud_still_works(self) -> None:
        from airunner_services.knowledge_crud import (
            _get_or_create_public_context,
        )
        assert callable(_get_or_create_public_context)


# ── EmailAccount ID scoping regression ──────────────────────────


class TestEmailAccountIdScoping:
    """FHE key material must be keyed off platform account_id, not
    EmailAccount.id (mailbox row ID)."""

    def test_compute_encrypted_embeddings_uses_account_id(self) -> None:
        with patch(
            "projects.uwuchat.server.embedding_provider"
            ".get_embedding_provider",
        ) as mock_provider, patch(
            "airunner_services.utils.crypto.fhe_account_context"
            ".get_or_create_public_context",
        ) as mock_get_ctx:
            mock_provider.return_value.embed_documents.return_value = (
                [[0.1] * 1024]
            )
            mock_get_ctx.return_value = MagicMock()

            from projects.uwuchat.server.email.email_body_indexer import (
                _compute_encrypted_embeddings,
            )

            result = _compute_encrypted_embeddings(
                ["chunk text"], account_id=42,
            )

            assert result is not None
            mock_get_ctx.assert_called_once_with(42)

    def test_compute_and_persist_resolves_account_id(self) -> None:
        from cryptography.fernet import Fernet

        from airunner_services.utils.crypto.dek_cache import dek_scope

        dek = Fernet.generate_key()

        with dek_scope(dek), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            ".session_scope",
        ), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            "._compute_encrypted_embeddings",
        ) as mock_compute, patch(
            "airunner_services.llm.token_usage.record_usage",
        ):
            mock_compute.return_value = [b"mock-ciphertext"]

            from projects.uwuchat.server.email.email_body_indexer import (
                _compute_and_persist,
            )
            from projects.uwuchat.server.email.provider import (
                EmailMessage,
            )

            msg = EmailMessage(
                provider_id="test1",
                thread_id="t1",
                mailbox_role="inbox",
                from_address="alice@example.com",
                to_addresses=[{"address": "bob@example.com"}],
                body_text="Test body.",
            )

            _compute_and_persist(
                email_account_id=99,
                thread_id="t1",
                chunks=["chunk"],
                messages=[msg],
                account_id=42,
            )

            mock_compute.assert_called_once_with(
                ["chunk"], 42,
            )

    def test_search_email_body_chunks_no_id_filter(self) -> None:
        import inspect
        from projects.uwuchat.server.email.email_rag import (
            search_email_body_chunks,
        )

        source = inspect.getsource(search_email_body_chunks)
        assert "email_account_id == account_id" not in source, (
            "search_email_body_chunks must not compare "
            "EmailBodyChunk.email_account_id (mailbox row ID) "
            "against account_id (platform account ID)"
        )
