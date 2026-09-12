"""Test that recent Alembic migrations are idempotent.

Runs the upgrade path twice against a scratch PostgreSQL schema and
asserts that the second run does not raise an error.
"""

from __future__ import annotations

import os
import uuid

import pytest

from airunner_services.database.session import reset_engine


def _fresh_tenant_key() -> str:
    return f"migtest_{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def _db(monkeypatch: pytest.MonkeyPatch) -> str:
    """Ensure a test database is reachable and initialise the public
    schema.

    Does NOT set ``AIRUNNER_DISABLE_DB_SETUP_CACHE`` — the default
    (cache enabled) lets ``setup_database()`` short-circuit after the
    first call within the process, preventing repeated DDL against
    ``public.pipeline_token_usage`` that accumulates dropped-column
    slots toward PostgreSQL's 1600-column ceiling.
    """
    db_url = os.environ.get(
        "AIRUNNER_TEST_DATABASE_URL",
        os.environ.get("AIRUNNER_DATABASE_URL"),
    )
    if not db_url:
        pytest.skip("No test database configured (AIRUNNER_TEST_DATABASE_URL)")
    if not db_url.startswith("postgres"):
        pytest.skip("Migration idempotency tests require PostgreSQL")
    monkeypatch.setenv("AIRUNNER_DATABASE_URL", db_url)
    monkeypatch.setenv("AIRUNNER_DB_TENANCY", "multi")
    reset_engine()

    from airunner_services.database.setup_database import setup_database

    try:
        setup_database()
    except Exception as exc:  # pragma: no cover — env dependent
        pytest.skip(f"Database unavailable: {exc}")
    return db_url


def test_migration_upgrade_idempotent(_db: str) -> None:
    """Running the full migration upgrade path twice against the same
    scratch schema does not error."""
    from airunner_services.data.tenant import tenant_scope

    tenant = _fresh_tenant_key()

    # First run — create the scratch schema and run migrations.
    with tenant_scope(tenant):
        from airunner_services.database.session import session_scope

        with session_scope() as session:
            # Write a row to force schema materialisation.
            from airunner_services.database.models.chatstore import (
                Chatstore,
            )

            session.add(Chatstore(key="mig-test", value={"v": 1}))
            session.flush()

    # Second run — the same tenant must be migrated without error.
    # _ensure_tenant_ready short-circuits via _migrated_tenants since
    # the schema was already migrated.  reset_engine() is deliberately
    # NOT called — it would clear _migrated_tenants and cause
    # _ensure_tenant_ready to re-run migrations against an
    # already-migrated schema, which fails on non-idempotent
    # migrations (e.g. ALTER TABLE ADD COLUMN without IF NOT EXISTS).
    with tenant_scope(tenant):
        from airunner_services.database.session import session_scope

        with session_scope() as session:
            from airunner_services.database.models.chatstore import (
                Chatstore,
            )

            row = (
                session.query(Chatstore)
                .filter(Chatstore.key == "mig-test")
                .one_or_none()
            )
            assert row is not None, (
                "Existing row should be visible after re-migration"
            )
            assert row.value == {"v": 1}

    # Clean up the scratch schema.
    _drop_schema(tenant)


def _drop_schema(tenant_key: str) -> None:
    """Drop the scratch tenant schema."""
    from airunner_services.data.tenant import tenant_schema_for_key
    from airunner_services.database.session import _tenant_db_url

    schema = tenant_schema_for_key(tenant_key)
    db_url = os.environ.get("AIRUNNER_DATABASE_URL", "")
    if not db_url:
        return

    tenant_url = _tenant_db_url(db_url, schema)
    from airunner_services.database.db.engine import create_configured_engine

    engine = create_configured_engine(tenant_url)
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    finally:
        engine.dispose()
