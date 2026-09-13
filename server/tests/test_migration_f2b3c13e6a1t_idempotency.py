"""Idempotency test for migration f2b3c13e6a1t.

Confirms that re-running upgrade() against a schema that already has
the event-lifecycle columns does not error and does not duplicate
data.
"""
from __future__ import annotations

import os
import uuid

import pytest

from airunner_services.database.session import reset_engine


def _fresh_tenant_key() -> str:
    return f"migtest_f2b3c13e6a1t_{uuid.uuid4().hex[:12]}"


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
    """Re-running f2b3c13e6a1t's upgrade() against a schema that
    already has the lifecycle columns must not raise and must not
    duplicate data."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope

    tenant = _fresh_tenant_key()

    try:
        # First run: apply the full migration chain, including
        # f2b3c13e6a1t.  This materialises the lifecycle columns
        # normally.
        with tenant_scope(tenant):
            with session_scope() as session:
                from airunner_services.database.models.chatstore import (
                    Chatstore,
                )

                session.add(
                    Chatstore(
                        key="mig-f2b3c13e6a1t-test",
                        value={"v": 1},
                    )
                )
                session.flush()

                # Insert a knowledge fact through the ORM to
                # confirm the columns exist and work.
                from airunner_services.database.models.knowledge_fact import (
                    KnowledgeFact,
                )
                import datetime

                fact = KnowledgeFact(
                    fact_text="test fact",
                    chatbot_id=1,
                    subject="user",
                    event_date=datetime.date(2026, 7, 26),
                    recurring=False,
                    temporal_status="upcoming",
                )
                session.add(fact)
                session.flush()
                fact_id = fact.id

        # Second run: reset_engine() clears _migrated_tenants,
        # causing _ensure_tenant_ready to re-run migrations against
        # the already-migrated schema.  The upgrade() function must
        # be idempotent — all _column_exists checks must return
        # True and skip the ADD COLUMN.
        reset_engine()

        with tenant_scope(tenant):
            with session_scope() as session:
                from airunner_services.database.models.knowledge_fact import (
                    KnowledgeFact,
                )

                # Row inserted before re-migration must still exist.
                fact = (
                    session.query(KnowledgeFact)
                    .filter(KnowledgeFact.id == fact_id)
                    .one_or_none()
                )
                assert fact is not None, (
                    "Existing fact row missing after re-migration"
                )
                assert fact.temporal_status == "upcoming"
                assert fact.event_date == datetime.date(2026, 7, 26)
                assert fact.recurring is False

                # Insert another fact to confirm the columns are
                # still usable.
                fact2 = KnowledgeFact(
                    fact_text="second fact",
                    chatbot_id=1,
                    subject="self",
                    event_date=datetime.date(2026, 8, 1),
                    event_end_date=datetime.date(2026, 8, 7),
                    recurring=False,
                    temporal_status="upcoming",
                )
                session.add(fact2)
                session.flush()
                assert fact2.id is not None

    finally:
        reset_engine()
        _drop_schema(tenant)
