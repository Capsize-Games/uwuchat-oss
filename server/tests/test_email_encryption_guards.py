"""Regression: email sync pipeline fails closed when DEK unavailable.

Part 2 — Guards against silent fallback to the global keyring or
plaintext when per-user DEK is not in context. Covers BOTH the
body-chunk write (``email_body_indexer._compute_and_persist`` — see
its own DEK-guard tests in test_email_body_indexer.py) and the
entity-name write (``extract_contacts`` → ``resolve_entity``), via
the ``_process_message_chunk`` guard that runs before either.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from airunner_services.utils.crypto.data_encryption import (
    DataEncryptionError,
)


class TestProcessMessageChunkDekGuard:
    """``_process_message_chunk`` must raise when no DEK is in context
    — covers BOTH entity-name encryption (contacts.py) and body-chunk
    encryption (email_body_indexer.py)."""

    def test_raises_when_no_dek(self) -> None:
        from projects.uwuchat.server.email.sync_pipeline import (
            _process_message_chunk,
        )

        with patch(
            "airunner_services.utils.crypto.dek_cache.get_user_dek",
            return_value=None,
        ):
            with pytest.raises(DataEncryptionError):
                _process_message_chunk(
                    1, 1, None, ["msg1"],
                )

    def test_succeeds_with_active_dek(self) -> None:
        """With DEK mocked, the chunk proceeds past the guard.  The
        rest is mocked to avoid real I/O.

        Note: ``index_thread_bodies`` was removed from this module
        when body indexing moved to a background task (Part 2), so
        it is no longer mocked here."""
        from cryptography.fernet import Fernet

        from airunner_services.utils.crypto.dek_cache import dek_scope
        from projects.uwuchat.server.email.sync_pipeline import (
            _process_message_chunk,
        )

        dek = Fernet.generate_key()

        with dek_scope(dek), patch(
            "projects.uwuchat.server.email.sync_pipeline"
            ".fetch_email_bodies",
            return_value=[],
        ), patch(
            "projects.uwuchat.server.email.sync_pipeline"
            "._update_automated_flags",
        ), patch(
            "projects.uwuchat.server.email.sync_pipeline"
            ".extract_contacts",
        ), patch(
            "projects.uwuchat.server.email.sync_pipeline"
            "._mark_processed",
        ), patch(
            "projects.uwuchat.server.email.sync_pipeline"
            "._get_threads_needing_reindex",
            return_value=set(),
        ):
            # Should not raise.
            _process_message_chunk(
                1, 1, None, ["msg1"],
            )
