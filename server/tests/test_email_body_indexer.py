"""Regression tests for email body chunking, embedding, and the DEK
fail-closed guard (replaces test_email_summarizer.py).

Part 1 — Verifies that thread text assembly and chunking produce
distinct, thread-specific output (regression: the old summarizer
produced identical placeholder text across every thread).

Part 2 — Verifies that ``_compute_and_persist`` raises
``DataEncryptionError`` on write when no DEK is available, instead of
silently falling back to the global keyring or plaintext.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)


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


class TestBuildThreadText:
    """``_build_thread_text`` must sort by sent_at and format each
    message as ``"{sender}: {body}"``."""

    def test_sorts_by_sent_at_and_formats_sender(self) -> None:
        from projects.uwuchat.server.email.email_body_indexer import (
            _build_thread_text,
        )

        first = _make_msg(
            "m1", "t1", "First message.", from_name="Alice",
            sent_at="2025-01-01T00:00:00Z",
        )
        second = _make_msg(
            "m2", "t1", "Second message.", from_name="Bob",
            sent_at="2025-01-02T00:00:00Z",
        )
        # Passed out of order; output must still be chronological.
        text = _build_thread_text([second, first])

        assert text.index("Alice: First message.") < text.index(
            "Bob: Second message.",
        )


class TestChunkThreadText:
    """The splitter used by ``index_thread_bodies`` must produce
    thread-specific chunks — direct regression guard for the old bug
    where every thread produced identical placeholder text."""

    def test_short_thread_produces_one_chunk(self) -> None:
        from projects.uwuchat.server.email.email_body_indexer import (
            _splitter,
        )

        chunks = _splitter.split_text("A short email body.")
        assert len(chunks) == 1

    def test_long_thread_produces_multiple_overlapping_chunks(
        self,
    ) -> None:
        from projects.uwuchat.server.email.email_body_indexer import (
            _splitter,
        )

        paragraph = (
            "This is a distinctive sentence about quarterly budget "
            "planning and vendor contracts. "
        )
        long_text = paragraph * 40  # well over the 512-char chunk size
        chunks = _splitter.split_text(long_text)

        assert len(chunks) > 1
        # Adjacent chunks must share overlap text (the splitter's
        # chunk_overlap=50), not be disjoint slices.
        assert chunks[0][-30:] in chunks[1] or any(
            chunks[0][-20:] in c for c in chunks[1:]
        )

    def test_different_threads_produce_different_chunks(self) -> None:
        from projects.uwuchat.server.email.email_body_indexer import (
            _build_thread_text,
            _splitter,
        )

        thread_a = [_make_msg(
            "a1", "thread_a",
            "We need to finalize the Q3 budget by Friday. The "
            "marketing team requested fifty thousand dollars more.",
        )]
        thread_b = [_make_msg(
            "b1", "thread_b",
            "The server migration is scheduled for next weekend. "
            "All services will be down from Saturday midnight.",
        )]

        chunks_a = _splitter.split_text(_build_thread_text(thread_a))
        chunks_b = _splitter.split_text(_build_thread_text(thread_b))

        assert chunks_a != chunks_b
        assert "budget" in chunks_a[0]
        assert "migration" in chunks_b[0]
        assert "budget" not in chunks_b[0]
        assert "migration" not in chunks_a[0]

    def test_empty_body_produces_no_meaningful_chunks(self) -> None:
        """An empty body still leaves the sender-label text (e.g.
        "Alice:") — that's fine, it just must not crash and must not
        produce more than one trivial chunk."""
        from projects.uwuchat.server.email.email_body_indexer import (
            _build_thread_text,
            _splitter,
        )

        msg = _make_msg("m1", "thread_empty", "")
        text = _build_thread_text([msg])
        chunks = _splitter.split_text(text) if text.strip() else []
        assert len(chunks) <= 1
        if chunks:
            assert len(chunks[0]) < 20


class TestComputeAndPersistDekGuard:
    """``_compute_and_persist`` must raise ``DataEncryptionError``
    when no per-user DEK is in context, preventing silent fallback to
    the global keyring for email body content."""

    def test_raises_when_no_dek(self) -> None:
        from projects.uwuchat.server.email.email_body_indexer import (
            _compute_and_persist,
        )
        from projects.uwuchat.server.email.provider import EmailMessage

        msg = EmailMessage(
            provider_id="test1",
            thread_id="test_thread",
            mailbox_role="inbox",
            from_address="alice@example.com",
            to_addresses=[{"address": "bob@example.com"}],
            body_text="Test email body.",
        )

        with pytest.raises(DataEncryptionError):
            _compute_and_persist(
                1, "test_thread", ["Test chunk."], [msg],
                account_id=1,
            )

    def test_succeeds_with_active_dek(self) -> None:
        from cryptography.fernet import Fernet

        from airunner_services.utils.crypto.dek_cache import dek_scope
        from projects.uwuchat.server.email.provider import EmailMessage

        msg = EmailMessage(
            provider_id="test1",
            thread_id="test_thread",
            mailbox_role="inbox",
            from_address="alice@example.com",
            to_addresses=[{"address": "bob@example.com"}],
            body_text="Test email body.",
        )

        dek = Fernet.generate_key()

        with dek_scope(dek), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            ".session_scope",
        ), patch(
            "projects.uwuchat.server.email.email_body_indexer"
            "._compute_encrypted_embeddings",
            return_value=[b"\x00"],
        ):
            from projects.uwuchat.server.email.email_body_indexer import (
                _compute_and_persist,
            )

            # Should not raise.
            _compute_and_persist(
                1, "test_thread", ["Test chunk."], [msg],
                account_id=1,
            )
