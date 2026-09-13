"""Regression tests for batched email body indexing throughput.

Verifies the batch-embedding and batch-JMAP-fetch redesign in
``email_body_indexer.py``, ``email_indexing_tasks.py``, and
``sync_body_fetch.py``.

Test coverage (matching the plan's test spec):
  1. Embedding call count drops — given N threads, the embedding
     provider's ``embed_documents`` is called far fewer than N times.
  2. Chunk-to-thread mapping stays correct — each persisted
     ``EmailBodyChunk`` row has the correct ``thread_id`` and
     ``chunk_index`` for its actual content.
  3. Progress still fires per thread, not per batch.
  4. One failed embed sub-batch doesn't take down the whole batch.
  5. Global JMAP concurrency gate — many concurrent simulated callers
     stay under ``_MAX_CONCURRENT_JMAP_REQUESTS``.
  6. Tenant/DEK propagation preserved in the batch worker function.
  7. Full existing test suite for this module still passes (verified
     by the run script, not by individual assertions here).

Does NOT hit a real embedding provider, real Fastmail API, or real
Redis/Postgres — mocks at the same boundaries as the existing tests.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)


# ---------------------------------------------------------------------------
# Shared fixtures — these keep the test file container-safe by patching
# external dependencies that hit real Redis or other infrastructure.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_is_cancelled() -> None:
    """Prevent ``index_thread_bodies`` from hitting real Redis.

    ``is_cancelled`` in ``email_body_indexer.py`` is a module-level
    import from ``.sync_cancellation``, which calls ``cache_redis()``
    and hits a live Redis instance.  Without this patch, a stale
    cancellation key from any other test (e.g. ``cancel_sync(1)`` with
    a 1-hour TTL) causes ``index_thread_bodies`` to exit its loop
    immediately on the first thread — silently producing zero results
    even though every mock is correctly wired.

    The patch target is the *consumer* module
    (``email_body_indexer.is_cancelled``), not the source module
    (``sync_cancellation.is_cancelled``), because the import is
    module-level in ``email_body_indexer.py`` and creates a module
    attribute.  For ``_fetch_and_index_thread_batch``, which does a
    *function-internal* lazy import of ``is_cancelled`` from
    ``sync_cancellation``, tests that exercise that path must add
    their own patch at the source module.
    """
    with patch(
        "projects.uwuchat.server.email.email_body_indexer"
        ".is_cancelled",
        return_value=False,
    ):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_msg(
    provider_id: str,
    thread_id: str,
    body_text: str,
    from_address: str = "alice@example.com",
    from_name: str = "Alice",
    sent_at: str | None = None,
):
    """Build a minimal EmailMessage dataclass for testing."""
    from projects.uwuchat.server.email.provider import EmailMessage

    return EmailMessage(
        provider_id=provider_id,
        thread_id=thread_id,
        mailbox_role="inbox",
        from_address=from_address,
        from_name=from_name,
        to_addresses=[{"address": "bob@example.com", "name": "Bob"}],
        body_text=body_text,
        sent_at=sent_at or "2025-01-01T00:00:00Z",
    )


def _make_messages(thread_count: int, chunks_per_thread: int = 2):
    """Build *thread_count* threads each with 1 message of usable text
    that splits into roughly *chunks_per_thread* chunks."""
    messages = []
    for t in range(thread_count):
        tid = f"thread_{t}"
        paragraph = (
            "This is a distinctive sentence for thread "
            f"{tid} about quarterly budget planning and vendor "
            "contracts and the annual performance review cycle. "
        )
        body = paragraph * (chunks_per_thread * 10)
        messages.append(_make_msg(
            f"msg_{t}", tid, body,
        ))
    return messages


def _make_messages_exact_chunks(
    thread_count: int, chunk_count: int,
):
    """Build *thread_count* threads where each thread's body text
    splits into exactly *chunk_count* chunks."""
    from projects.uwuchat.server.email.email_body_indexer import (
        _splitter,
    )

    messages = []
    sentence = (
        "Short sentence about vendor budget planning and review. "
    )
    for t in range(thread_count):
        tid = f"thread_{t}"
        # Find a body length that produces exactly chunk_count chunks
        for multiplier in range(1, 100):
            body = sentence * (chunk_count * multiplier)
            chunks = _splitter.split_text(body)
            if len(chunks) == chunk_count:
                break
        messages.append(_make_msg(f"msg_{t}", tid, body))
    return messages


# ---------------------------------------------------------------------------
# Test 1: Embedding call count drops
# ---------------------------------------------------------------------------


class TestEmbeddingCallCountDrops:
    """Given messages spanning N threads in one ``index_thread_bodies``
    call, the embedding provider's ``embed_documents`` is called far
    fewer than N times (bounded by ``_EMBEDDING_BATCH_SIZE``)."""

    def test_embedding_called_less_than_thread_count(self) -> None:
        """10 threads with ~2 chunks each = ~20 chunks = 1 embedding
        call (at ``_EMBEDDING_BATCH_SIZE=500``), vs 10 calls before."""
        from projects.uwuchat.server.email.email_body_indexer import (
            index_thread_bodies,
        )
        from cryptography.fernet import Fernet

        from airunner_services.utils.crypto.dek_cache import dek_scope

        dek = Fernet.generate_key()
        messages = _make_messages(thread_count=10)

        call_count = 0

        def _counting_embed(chunks, account_id):
            nonlocal call_count
            call_count += 1
            return [b"\x00" for _ in chunks]

        with dek_scope(dek), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            ".session_scope",
        ), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            "._compute_encrypted_embeddings",
            side_effect=_counting_embed,
        ), patch(
            "airunner_services.llm.token_usage.record_usage",
        ):
            result = index_thread_bodies(
                1, messages, account_id=1,
            )

        assert result == 10, f"Expected 10 threads indexed, got {result}"
        assert call_count <= 1, (
            f"Expected at most 1 embedding call for 10 threads "
            f"with ~20 total chunks, got {call_count}"
        )

    def test_large_batch_proportional_calls(self) -> None:
        """A batch large enough to exceed _EMBEDDING_BATCH_SIZE should
        result in the right number of sub-batch calls."""
        from projects.uwuchat.server.email.email_body_indexer import (
            index_thread_bodies,
        )
        from cryptography.fernet import Fernet

        from airunner_services.utils.crypto.dek_cache import dek_scope

        dek = Fernet.generate_key()
        # 300 threads × 2 chunks each = 600 chunks.
        # At _EMBEDDING_BATCH_SIZE=500: ceil(600/500) = 2 calls.
        messages = _make_messages_exact_chunks(
            thread_count=300, chunk_count=2,
        )

        call_count = 0

        def _counting_embed(chunks, account_id):
            nonlocal call_count
            call_count += 1
            return [b"\x00" for _ in chunks]

        with dek_scope(dek), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            ".session_scope",
        ), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            "._compute_encrypted_embeddings",
            side_effect=_counting_embed,
        ), patch(
            "airunner_services.llm.token_usage.record_usage",
        ):
            index_thread_bodies(1, messages, account_id=1)

        assert call_count == 2, (
            f"Expected 2 embedding calls for 300 threads "
            f"(2 chunks each = 600 chunks), got {call_count}"
        )


# ---------------------------------------------------------------------------
# Test 2: Chunk-to-thread mapping stays correct
# ---------------------------------------------------------------------------


class TestChunkToThreadMapping:
    """Each persisted ``EmailBodyChunk`` row still has the right
    ``thread_id`` and ``chunk_index`` for its actual content, even when
    multiple threads' chunks were embedded in the same API call."""

    def test_chunks_have_correct_thread_ids(self) -> None:
        from projects.uwuchat.server.email.email_body_indexer import (
            index_thread_bodies,
        )
        from cryptography.fernet import Fernet

        from airunner_services.utils.crypto.dek_cache import dek_scope

        from airunner_services.database.models.email_body_chunk import (
            EmailBodyChunk,
        )

        dek = Fernet.generate_key()

        # Two threads with distinct content.
        msgs = [
            _make_msg("m1", "thread_a", "Budget planning Q3."),
            _make_msg("m2", "thread_b", "Server migration plan."),
        ]

        added_rows: list[EmailBodyChunk] = []

        def _capture_add(row):
            added_rows.append(row)

        with dek_scope(dek), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            ".session_scope",
        ) as mock_scope, patch(
            "projects.uwuchat.server.email.email_body_indexer"
            "._compute_encrypted_embeddings",
            return_value=[b"\x00", b"\x01"],
        ), patch(
            "airunner_services.llm.token_usage.record_usage",
        ):
            mock_session = MagicMock()
            mock_scope.return_value.__enter__.return_value = mock_session
            mock_session.add.side_effect = _capture_add

            index_thread_bodies(1, msgs, account_id=1)

        thread_a_rows = [
            r for r in added_rows if r.thread_id == "thread_a"
        ]
        thread_b_rows = [
            r for r in added_rows if r.thread_id == "thread_b"
        ]

        assert len(thread_a_rows) >= 1, (
            "Expected at least 1 EmailBodyChunk for thread_a"
        )
        assert len(thread_b_rows) >= 1, (
            "Expected at least 1 EmailBodyChunk for thread_b"
        )
        assert all(
            r.chunk_index == i for i, r in enumerate(thread_a_rows)
        ), "chunk_index must be sequential for thread_a"
        assert all(
            r.chunk_index == i for i, r in enumerate(thread_b_rows)
        ), "chunk_index must be sequential for thread_b"
        assert all(
            "budget" in r.content_ciphertext.lower()
            for r in thread_a_rows
        ), "thread_a content must reference budget"
        assert all(
            "server" in r.content_ciphertext.lower()
            for r in thread_b_rows
        ), "thread_b content must reference server"


# ---------------------------------------------------------------------------
# Test 3: Progress still fires per thread
# ---------------------------------------------------------------------------


class TestProgressFiresPerThread:
    """``on_progress`` is called once per thread processed, in a batch
    of several threads, not once total."""

    def test_progress_called_per_thread(self) -> None:
        from projects.uwuchat.server.email.email_body_indexer import (
            index_thread_bodies,
        )
        from cryptography.fernet import Fernet

        from airunner_services.utils.crypto.dek_cache import dek_scope

        dek = Fernet.generate_key()
        messages = _make_messages(thread_count=5)
        progress_calls: list[tuple[int, int]] = []

        def _on_progress(done, total):
            progress_calls.append((done, total))

        with dek_scope(dek), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            ".session_scope",
        ), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            "._compute_encrypted_embeddings",
            return_value=[b"\x00"] * 50,
        ), patch(
            "airunner_services.llm.token_usage.record_usage",
        ):
            result = index_thread_bodies(
                1, messages,
                on_progress=_on_progress, account_id=1,
            )

        assert result == 5, f"Expected 5 threads indexed, got {result}"
        assert len(progress_calls) == 5, (
            f"Expected 5 progress callbacks (one per thread), "
            f"got {len(progress_calls)}"
        )
        for i, (done, total) in enumerate(progress_calls):
            assert done == i + 1, (
                f"Expected done={i + 1} on callback {i}, got {done}"
            )
            assert total == 5, (
                f"Expected total=5 on callback {i}, got {total}"
            )


# ---------------------------------------------------------------------------
# Test 4: One failed embed sub-batch doesn't take down the whole batch
# ---------------------------------------------------------------------------


class TestFailedEmbedSubBatch:
    """Chunks in a failed sub-batch get ``embedding_enc = None``;
    chunks in other sub-batches within the same run still get real
    embeddings."""

    def test_failed_subbatch_gets_none(self) -> None:
        """Mock ``_compute_encrypted_embeddings`` to return real
        embeddings for the first sub-batch and None for subsequent
        ones — verifying the batch survives partial failure."""
        from projects.uwuchat.server.email.email_body_indexer import (
            index_thread_bodies,
        )
        from cryptography.fernet import Fernet

        from airunner_services.utils.crypto.dek_cache import dek_scope

        from airunner_services.database.models.email_body_chunk import (
            EmailBodyChunk,
        )

        dek = Fernet.generate_key()
        messages = _make_messages_exact_chunks(
            thread_count=600, chunk_count=1,
        )
        # 600 threads × 1 chunk = 600 chunks.
        # At _EMBEDDING_BATCH_SIZE=500: 2 sub-batches (500 + 100).

        added_rows: list[EmailBodyChunk] = []

        def _capture_add(row):
            added_rows.append(row)

        call_count = 0

        def _failing_embed_wrapper(chunks, account_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [b"\x00" for _ in chunks]
            return [None] * len(chunks)

        with dek_scope(dek), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            ".session_scope",
        ) as mock_scope, patch(
            "projects.uwuchat.server.email.email_body_indexer"
            "._compute_encrypted_embeddings",
            side_effect=_failing_embed_wrapper,
        ), patch(
            "airunner_services.llm.token_usage.record_usage",
        ):
            mock_session = MagicMock()
            mock_scope.return_value.__enter__.return_value = mock_session
            mock_session.add.side_effect = _capture_add

            index_thread_bodies(1, messages, account_id=1)

        rows_with_real = [
            r for r in added_rows if r.embedding_enc is not None
        ]
        rows_with_none = [
            r for r in added_rows if r.embedding_enc is None
        ]

        assert len(rows_with_real) >= 500, (
            f"Expected at least 500 rows with real embeddings "
            f"(first sub-batch), got {len(rows_with_real)}"
        )
        assert len(rows_with_none) >= 100, (
            f"Expected at least 100 rows with None embeddings "
            f"(failed sub-batch), got {len(rows_with_none)}"
        )

    def test_first_exception_does_not_abort_whole_run(self) -> None:
        """The exception handler inside ``_compute_encrypted_embeddings``
        catches errors and returns [None]*N, not propagates. Verifies
        by mocking ``get_embedding_provider`` to raise on the first
        call, not by mocking ``_compute_encrypted_embeddings`` itself,
        so the real exception handler runs."""
        from projects.uwuchat.server.email.email_body_indexer import (
            index_thread_bodies,
        )
        from cryptography.fernet import Fernet

        from airunner_services.utils.crypto.dek_cache import dek_scope

        dek = Fernet.generate_key()
        # Need enough chunks to span 2 sub-batches.
        messages = _make_messages_exact_chunks(
            thread_count=600, chunk_count=1,
        )

        call_count = 0

        def _raising_embed_documents(texts, priority="live"):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Embedding provider down")
            # Second call works
            return [[0.1] * 1024 for _ in texts]

        with dek_scope(dek), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            ".session_scope",
        ), patch(
            "projects.uwuchat.server.embedding_provider"
            ".get_embedding_provider",
        ) as mock_get_provider, patch(
            "airunner_services.utils.crypto.fhe_account_context"
            ".get_or_create_public_context",
        ), patch(
            "airunner_services.utils.crypto.fhe_helpers"
            ".encrypt_embedding",
            return_value=b"\x00",
        ), patch(
            "airunner_services.utils.crypto.fhe_helpers"
            ".l2_normalize",
            side_effect=lambda v: v,
        ), patch(
            "airunner_services.llm.token_usage.record_usage",
        ):
            mock_provider = MagicMock()
            mock_provider.embed_documents.side_effect = (
                _raising_embed_documents
            )
            mock_get_provider.return_value = mock_provider

            result = index_thread_bodies(
                1, messages, account_id=1,
            )

        # All 600 threads should be counted as indexed despite the
        # first embed call failing — first sub-batch gets None
        # embeddings, second gets real embeddings.
        assert result == 600, (
            f"Expected 600 threads indexed despite partial failure, "
            f"got {result}"
        )
        assert call_count == 2, (
            f"Expected 2 embed calls (first fails, second succeeds), "
            f"got {call_count}"
        )


# ---------------------------------------------------------------------------
# Test 5: Global JMAP concurrency gate
# ---------------------------------------------------------------------------


class TestGlobalJmapConcurrencyGate:
    """No more than ``_MAX_CONCURRENT_JMAP_REQUESTS`` JMAP HTTP requests
    are ever in-flight simultaneously, regardless of the number of
    concurrent callers."""

    def test_semaphore_limits_concurrent_requests(self) -> None:
        from projects.uwuchat.server.email.sync_body_fetch import (
            _MAX_CONCURRENT_JMAP_REQUESTS,
            fetch_email_bodies,
        )

        max_concurrent = 0
        current_concurrent = 0
        lock = threading.Lock()

        async def _slow_get_emails(ids):
            nonlocal max_concurrent, current_concurrent
            with lock:
                current_concurrent += 1
                max_concurrent = max(
                    max_concurrent, current_concurrent,
                )
            time.sleep(0.1)
            with lock:
                current_concurrent -= 1
            return []

        mock_provider = MagicMock()
        mock_provider.get_emails = _slow_get_emails

        ids = {str(i) for i in range(1000)}

        def _caller():
            fetch_email_bodies(mock_provider, ids)

        threads = [
            threading.Thread(target=_caller) for _ in range(6)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert max_concurrent <= _MAX_CONCURRENT_JMAP_REQUESTS, (
            f"Exceeded max concurrent JMAP requests: "
            f"{max_concurrent} > {_MAX_CONCURRENT_JMAP_REQUESTS}"
        )

    def test_semaphore_release_on_exception(self) -> None:
        """The semaphore must be released even when
        ``provider.get_emails`` raises — otherwise the semaphore
        leaks and permanently blocks future requests."""
        from projects.uwuchat.server.email.sync_body_fetch import (
            _MAX_CONCURRENT_JMAP_REQUESTS,
            _jmap_concurrency_semaphore,
            fetch_email_bodies,
        )

        mock_provider = MagicMock()
        mock_provider.get_emails = MagicMock(
            side_effect=RuntimeError("JMAP API error"),
        )

        ids = {"1", "2", "3"}

        with pytest.raises(RuntimeError, match="JMAP API error"):
            fetch_email_bodies(mock_provider, ids)

        # After the error, the semaphore should be fully available.
        available = _jmap_concurrency_semaphore._value
        assert available == _MAX_CONCURRENT_JMAP_REQUESTS, (
            f"Semaphore leaked: {available} permits available, "
            f"expected {_MAX_CONCURRENT_JMAP_REQUESTS}"
        )


# ---------------------------------------------------------------------------
# Test 6: Tenant/DEK propagation preserved in batch worker
# ---------------------------------------------------------------------------


class TestBatchWorkerTenantDekPropagation:
    """The new batch worker function ``_fetch_and_index_thread_batch``
    must enter ``tenant_scope``/``dek_scope`` from the passed arguments
    rather than relying on inherited context.

    The worker function uses lazy imports inside its body
    (``from airunner_services.data.tenant import tenant_scope``), so
    patching must target the *source* module
    (``airunner_services.data.tenant.tenant_scope``), not the worker's
    module, which only has a local variable at runtime.
    """

    def test_tenant_scope_entered_in_worker(self) -> None:
        """Verify that tenant_scope is called with the right key
        inside the batch worker."""
        from projects.uwuchat.server.tasks.email_indexing_tasks import (
            _fetch_and_index_thread_batch,
        )

        mock_provider = MagicMock()
        mock_provider.get_emails = MagicMock(return_value=[])

        with patch(
            "airunner_services.data.tenant.tenant_scope",
        ) as mock_tenant_scope, patch(
            "airunner_services.utils.crypto.dek_cache.dek_scope",
        ), patch(
            "airunner_services.database.session.session_scope",
        ), patch(
            "airunner_services.database.models.email_message"
            ".EmailMessage",
        ):
            _fetch_and_index_thread_batch(
                email_account_id=1,
                thread_ids=["t1", "t2"],
                provider=mock_provider,
                account_id=999,
                tenant_key="test_tenant_key",
                dek=b"test_dek_bytes",
                on_progress=lambda d, t: None,
            )

        mock_tenant_scope.assert_called_once_with("test_tenant_key")

    def test_dek_scope_entered_in_worker(self) -> None:
        """Verify that dek_scope is called with the right DEK
        inside the batch worker."""
        from projects.uwuchat.server.tasks.email_indexing_tasks import (
            _fetch_and_index_thread_batch,
        )

        mock_provider = MagicMock()
        mock_provider.get_emails = MagicMock(return_value=[])

        with patch(
            "airunner_services.data.tenant.tenant_scope",
        ), patch(
            "airunner_services.utils.crypto.dek_cache.dek_scope",
        ) as mock_dek_scope, patch(
            "airunner_services.database.session.session_scope",
        ), patch(
            "airunner_services.database.models.email_message"
            ".EmailMessage",
        ):
            _fetch_and_index_thread_batch(
                email_account_id=1,
                thread_ids=["t1", "t2"],
                provider=mock_provider,
                account_id=999,
                tenant_key="test_tenant",
                dek=b"test_dek_bytes",
                on_progress=lambda d, t: None,
            )

        mock_dek_scope.assert_called_once_with(b"test_dek_bytes")

    def test_batch_worker_raises_without_dek(self) -> None:
        """Indexing without an active DEK must raise
        ``DataEncryptionError`` even in the batch path (regression
        guard — the new batch ``index_thread_bodies`` must still
        enforce the DEK fail-closed guarantee)."""
        from projects.uwuchat.server.email.email_body_indexer import (
            index_thread_bodies,
        )

        messages = _make_messages(thread_count=2)

        with pytest.raises(DataEncryptionError):
            index_thread_bodies(1, messages, account_id=1)

    def test_batch_worker_succeeds_with_active_dek(self) -> None:
        """With DEK mocked, the batch indexer proceeds past the guard
        (mirrors ``test_succeeds_with_active_dek`` in the existing
        test suite)."""
        from projects.uwuchat.server.email.email_body_indexer import (
            index_thread_bodies,
        )
        from cryptography.fernet import Fernet

        from airunner_services.utils.crypto.dek_cache import dek_scope

        dek = Fernet.generate_key()
        messages = _make_messages(thread_count=2)

        with dek_scope(dek), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            ".session_scope",
        ), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            "._compute_encrypted_embeddings",
            return_value=[b"\x00"] * 10,
        ), patch(
            "airunner_services.llm.token_usage.record_usage",
        ):
            result = index_thread_bodies(
                1, messages, account_id=1,
            )

        assert result == 2, f"Expected 2 threads indexed, got {result}"


# ---------------------------------------------------------------------------
# Test 7: Existing tests still pass
# ---------------------------------------------------------------------------
# This is verified by running the full test suite, not by assertions
# in this file.  See the CI/task runner for that confirmation.
