"""Regression tests for email body-chunk retrieval (email_rag.py).

Structural/mocked tests only — full integration tests with a real
database belong in a DB-fixture test suite, per this repo's existing
convention (see test_tenant_isolation.py's module docstring).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestSearchEmailBodyChunks:
    def test_empty_query_returns_empty_list(self) -> None:
        from projects.uwuchat.server.email.email_rag import (
            search_email_body_chunks,
        )

        assert search_email_body_chunks("") == []
        assert search_email_body_chunks("   ") == []

    def test_embed_failure_returns_empty_list(self) -> None:
        from projects.uwuchat.server.email.email_rag import (
            search_email_body_chunks,
        )

        with patch(
            "projects.uwuchat.server.embedding_provider"
            ".get_embedding_provider",
            side_effect=RuntimeError("no api key"),
        ):
            assert search_email_body_chunks("budget") == []

    def test_queries_email_body_chunk_and_filters_null_embeddings(
        self,
    ) -> None:
        """Regression: must query EmailBodyChunk (not the deleted
        EmailThreadSummary), filter out rows with no embedding_enc, and
        decrypt content_ciphertext from the matched rows.

        Updated for privacy-hardening round 2: embedding → embedding_enc
        and FHE-scored results (now returns row.content_ciphertext directly
        rather than a tuple)."""
        from airunner_services.database.models.email_body_chunk import (
            EmailBodyChunk,
        )

        mock_provider = MagicMock()
        mock_provider.embed_query.return_value = [0.1, 0.2, 0.3]

        row = MagicMock()
        row.content_ciphertext = "decrypted excerpt text"
        row.embedding_enc = b"mock-ciphertext"

        with patch(
            "projects.uwuchat.server.embedding_provider"
            ".get_embedding_provider",
            return_value=mock_provider,
        ), patch(
            "airunner_services.data.tenant.get_account_id",
            return_value=123,
        ), patch.object(
            EmailBodyChunk, "objects",
        ) as mock_objects, patch(
            "airunner_services.utils.crypto.fhe_search"
            ".fhe_similarity_rank",
            return_value=[(row, 0.95)],
        ), patch(
            "airunner_services.llm.token_usage.record_usage",
        ):
            mock_objects.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
            from projects.uwuchat.server.email.email_rag import (
                search_email_body_chunks,
            )
            results = search_email_body_chunks("budget", k=8)

        assert results == ["decrypted excerpt text"]
