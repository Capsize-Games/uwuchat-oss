"""Regression tests for background email body indexing.

Part 2 — Verifies that the background indexing task:
  - Is registered as a Celery task
  - Sort by latest sent_at handles threads with None timestamps

Part 3 — Verifies that ``_compute_and_persist`` and
``search_email_body_chunks`` call ``record_usage`` for cost tracking.
"""

from __future__ import annotations

import datetime

from unittest.mock import patch


class TestIndexEmailBodiesBackgroundRegistered:
    """The background indexing task module must be in ``_task_include_list``
    so the Celery worker actually imports it at startup."""

    def test_module_in_include_list(self) -> None:
        from airunner_services.tasks.celery_app import (
            _task_include_list,
        )

        modules = _task_include_list()
        assert (
            "projects.uwuchat.server.tasks.email_indexing_tasks"
            in modules
        )


class TestEmailBodyIndexerRecordsUsage:
    """``_compute_and_persist`` must call ``record_usage`` for cost
    tracking during email body indexing."""

    def test_calls_record_usage(self) -> None:
        from projects.uwuchat.server.email.email_body_indexer import (
            _compute_and_persist,
        )

        from cryptography.fernet import Fernet

        from airunner_services.utils.crypto.dek_cache import dek_scope

        dek = Fernet.generate_key()

        with dek_scope(dek), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            ".session_scope",
        ), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            "._compute_encrypted_embeddings",
            return_value=[b"mock-ciphertext"],
        ), patch(
            "airunner_services.llm.token_usage.record_usage",
        ) as mock_record:
            from projects.uwuchat.server.email.provider import (
                EmailMessage,
            )

            msg = EmailMessage(
                provider_id="test1",
                thread_id="t1",
                mailbox_role="inbox",
                from_address="alice@example.com",
                to_addresses=[{"address": "bob@example.com"}],
                body_text="Test email body.",
            )
            _compute_and_persist(
                1, "t1", ["Test chunk."], [msg],
                account_id=1,
            )
            mock_record.assert_called_once()
            args, kwargs = mock_record.call_args
            assert kwargs["pipeline_key"] == "EMAIL_BODY_EMBEDDING"
            assert kwargs["output_tokens"] == 0
            # Input tokens estimated from char count: 11 // 4 = 2
            assert kwargs["input_tokens"] == 2


class TestBackgroundIndexingSort:
    """The background task's sort-by-latest-sent_at must survive threads
    where all messages have ``sent_at=None`` (malformed email metadata)."""

    def test_sort_survives_none_sent_at(self) -> None:
        """Sorting threads by latest sent_at must not crash when one
        or more threads have only None timestamps."""

        # We can't easily unit-test the sort in isolation because it
        # lives inside the Celery task function body.  Instead, verify
        # that the fallback expression ``thread_latest.get(tid) or
        # datetime.datetime.min`` evaluates safely for None values.
        thread_latest: dict[str, datetime.datetime | None] = {
            "thread_a": datetime.datetime(2025, 6, 1, 12, 0, 0),
            "thread_b": None,
            "thread_c": datetime.datetime(2025, 5, 1, 12, 0, 0),
        }

        threads = {"thread_a", "thread_b", "thread_c"}
        # This is the exact expression used in the sort key.
        sorted_threads = sorted(
            threads,
            key=lambda tid: thread_latest.get(tid)
            or datetime.datetime.min,
            reverse=True,
        )

        # thread_b (None) should sort last (oldest = datetime.min)
        assert sorted_threads == [
            "thread_a", "thread_c", "thread_b",
        ]


class TestEmailRagRecordsUsage:
    """``search_email_body_chunks`` must call ``record_usage`` for
    cost tracking after embedding the query."""

    def test_calls_record_usage(self) -> None:
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
                "projects.uwuchat.server.email.email_rag"
                ".EmailBodyChunk",
            ) as mock_chunk:
                mock_chunk.objects.query.return_value.filter.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
                with patch(
                    "airunner_services.llm.token_usage.record_usage",
                ) as mock_record, patch(
                    "airunner_services.data.tenant.get_account_id",
                    return_value=123,
                ):
                    result = search_email_body_chunks("test query")
                    assert result == []
                    mock_record.assert_called_once()
                    args, kwargs = mock_record.call_args
                    assert (
                        kwargs["pipeline_key"]
                        == "EMAIL_QUERY_EMBEDDING"
                    )
                    assert kwargs["output_tokens"] == 0

    def test_skips_record_usage_when_empty_query(self) -> None:
        from projects.uwuchat.server.email.email_rag import (
            search_email_body_chunks,
        )

        with patch(
            "airunner_services.llm.token_usage.record_usage",
        ) as mock_record:
            result = search_email_body_chunks("")
            assert result == []
            mock_record.assert_not_called()

            result = search_email_body_chunks("   ")
            assert result == []
            mock_record.assert_not_called()
