"""Encryption-at-rest tests for EmailMessage metadata columns.

Verifies that after encryption, raw column values read via direct SQL
do not contain the original plaintext subject, addresses, or names.
Mirrors the pattern used by existing encryption-at-rest tests for
other UserEncryptedText columns.
"""

from __future__ import annotations

import json
import os

import pytest

from airunner_services.utils.crypto.dek_cache import dek_scope
from airunner_services.utils.crypto.user_envelope import generate_dek


# Skip if no test database is configured.
requires_test_db = pytest.mark.skipif(
    not os.environ.get("AIRUNNER_TEST_DATABASE_URL"),
    reason="AIRUNNER_TEST_DATABASE_URL not configured",
)


def _raw_column_value(session, table: str, column: str, row_id: int):
    """Return the raw (undecrypted) value of one column from one row."""
    from sqlalchemy import text

    result = session.execute(
        text(
            f"SELECT {column} FROM {table} WHERE id = :row_id"
        ),
        {"row_id": row_id},
    ).scalar()
    return result


class TestEmailMessageMetadataEncryption:
    """Insert an EmailMessage with a per-user DEK, then assert the
    stored ciphertext does not leak plaintext sender/recipient info."""

    @requires_test_db
    def test_encrypted_columns_do_not_leak_plaintext(self):
        """Raw SQL query against email_messages returns ciphertext,
        not the original plaintext values for encrypted columns."""
        from airunner_services.database.models.email_message import (
            EmailMessage,
        )
        from airunner_services.database.session import session_scope

        # Generate a per-user DEK (the production path uses a real
        # user envelope, but for this test a generated key simulates
        # the encryption path correctly).
        dek = generate_dek()
        plain_subject = "Test subject — sensitive info"
        plain_from_addr = "alice@example.com"
        plain_from_name = "Alice Tester"
        plain_to = json.dumps([{"address": "bob@example.com"}])
        plain_cc = json.dumps([{"address": "charlie@example.com"}])

        with dek_scope(dek):
            with session_scope() as session:
                msg = EmailMessage(
                    email_account_id=1,
                    provider_message_id="test-msg-001",
                    thread_id=None,
                    mailbox_role="inbox",
                    from_address=plain_from_addr,
                    from_name=plain_from_name,
                    to_addresses=plain_to,
                    cc_addresses=plain_cc,
                    subject=plain_subject,
                )
                session.add(msg)
                session.flush()
                row_id = msg.id

                # Read back via ORM — should decrypt transparently.
                loaded = session.query(EmailMessage).filter(
                    EmailMessage.id == row_id,
                ).first()
                assert loaded is not None
                assert loaded.subject == plain_subject
                assert loaded.from_address == plain_from_addr
                assert loaded.from_name == plain_from_name
                assert json.loads(loaded.to_addresses) == json.loads(
                    plain_to,
                )
                assert json.loads(loaded.cc_addresses) == json.loads(
                    plain_cc,
                )

                # Read raw column values — must NOT contain plaintext.
                raw_subject = _raw_column_value(
                    session, "email_messages", "subject", row_id,
                )
                raw_from_addr = _raw_column_value(
                    session, "email_messages", "from_address", row_id,
                )
                raw_from_name = _raw_column_value(
                    session, "email_messages", "from_name", row_id,
                )
                raw_to = _raw_column_value(
                    session, "email_messages", "to_addresses", row_id,
                )
                raw_cc = _raw_column_value(
                    session, "email_messages", "cc_addresses", row_id,
                )

                assert raw_subject is not None
                assert raw_from_addr is not None
                assert raw_from_name is not None
                assert raw_to is not None
                assert raw_cc is not None

                assert plain_subject not in str(raw_subject), (
                    "Raw subject column leaks plaintext"
                )
                assert plain_from_addr not in str(raw_from_addr), (
                    "Raw from_address column leaks plaintext"
                )
                assert plain_from_name not in str(raw_from_name), (
                    "Raw from_name column leaks plaintext"
                )
                # The JSON-serialized plaintext must not appear raw.
                assert "bob@example.com" not in str(raw_to), (
                    "Raw to_addresses column leaks plaintext"
                )
                assert "charlie@example.com" not in str(raw_cc), (
                    "Raw cc_addresses column leaks plaintext"
                )

                # Clean up the test row.
                session.delete(msg)
                session.flush()
