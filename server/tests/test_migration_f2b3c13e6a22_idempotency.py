"""Idempotency test for migration f2b3c13e6a22.

Confirms that re-running upgrade() against a schema that already has
the email-message PII columns converted to TEXT does not error and
does not lose data.
"""

from __future__ import annotations

import os
import uuid

import pytest

from airunner_services.database.session import reset_engine


def _fresh_tenant_key() -> str:
    return f"migtest_f2b3c13e6a22_{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def _db(monkeypatch: pytest.MonkeyPatch) -> str:
    """Ensure a test database is reachable and initialise the public
    schema.  Matches the pattern in test_migration_idempotency.py."""
    db_url = os.environ.get(
        "AIRUNNER_TEST_DATABASE_URL",
        os.environ.get("AIRUNNER_DATABASE_URL"),
    )
    if not db_url:
        pytest.skip(
            "No test database configured "
            "(AIRUNNER_TEST_DATABASE_URL)"
        )
    if not db_url.startswith("postgres"):
        pytest.skip(
            "Migration idempotency tests require PostgreSQL"
        )
    monkeypatch.setenv("AIRUNNER_DATABASE_URL", db_url)
    monkeypatch.setenv("AIRUNNER_DB_TENANCY", "multi")
    reset_engine()

    from airunner_services.database.setup_database import setup_database

    try:
        setup_database()
    except Exception as exc:  # pragma: no cover — env dependent
        pytest.skip(f"Database unavailable: {exc}")
    return db_url


def _drop_schema(tenant_key: str) -> None:
    """Drop the scratch tenant schema."""
    from airunner_services.data.tenant import tenant_schema_for_key
    from airunner_services.database.session import _tenant_db_url
    from airunner_services.database.db.engine import (
        create_configured_engine,
    )

    schema = tenant_schema_for_key(tenant_key)
    db_url = os.environ.get("AIRUNNER_DATABASE_URL", "")
    if not db_url:
        return

    tenant_url = _tenant_db_url(db_url, schema)
    engine = create_configured_engine(tenant_url)
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(
                text(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            )
    finally:
        engine.dispose()


def test_upgrade_is_idempotent(_db: str) -> None:
    """Re-running f2b3c13e6a22's upgrade() against an already-migrated
    schema must not raise and must preserve existing data."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope

    tenant = _fresh_tenant_key()

    try:
        # First run: apply the full migration chain, including
        # f2b3c13e6a22.  This converts the PII columns to TEXT.
        with tenant_scope(tenant):
            with session_scope() as session:
                from airunner_services.database.models.email_message import (
                    EmailMessage,
                )
                import datetime

                msg = EmailMessage(
                    email_account_id=1,
                    provider_message_id="mig-test-msg-1",
                    thread_id="mig-test-thread-1",
                    mailbox_role="received",
                    from_address="test@example.com",
                    from_name="Test User",
                    subject="Test Subject",
                    sent_at=datetime.datetime(
                        2026, 7, 30, 12, 0, 0,
                    ),
                    has_attachments=False,
                    is_automated=False,
                )
                session.add(msg)
                session.flush()
                msg_id = msg.id

        # Second run: reset_engine() clears _migrated_tenants,
        # causing _ensure_tenant_ready to re-run migrations against
        # the already-migrated schema.  The upgrade() function must
        # be idempotent — all _column_info checks must see the
        # columns are already TEXT and skip the ALTER.
        reset_engine()

        with tenant_scope(tenant):
            with session_scope() as session:
                from airunner_services.database.models.email_message import (
                    EmailMessage,
                )

                # Row inserted before re-migration must still exist.
                msg = (
                    session.query(EmailMessage)
                    .filter(EmailMessage.id == msg_id)
                    .one_or_none()
                )
                assert msg is not None, (
                    "Existing email message row missing after "
                    "re-migration"
                )
                assert msg.subject == "Test Subject"
                assert msg.from_address == "test@example.com"

                # Insert another message to confirm the columns are
                # still usable.
                import datetime

                msg2 = EmailMessage(
                    email_account_id=1,
                    provider_message_id="mig-test-msg-2",
                    thread_id="mig-test-thread-2",
                    mailbox_role="sent",
                    from_address="sender@example.com",
                    from_name="Sender",
                    subject="Second Subject",
                    sent_at=datetime.datetime(
                        2026, 7, 30, 12, 30, 0,
                    ),
                    has_attachments=False,
                    is_automated=False,
                )
                session.add(msg2)
                session.flush()
                assert msg2.id is not None

    finally:
        reset_engine()
        _drop_schema(tenant)
