"""Regression test for migration f2b3c13e6a1n's idempotency bug.

Part 4 — round-8 security remediation. ``upgrade()`` guarded its
``CREATE TABLE`` on table-existence but not its ``CREATE INDEX ...
(embedding ...)`` on column-existence.  A later migration
(f2b3c13e6a1q) drops the ``embedding`` column entirely once a schema
has moved past it, so re-running f2b3c13e6a1n's ``upgrade()`` against
a schema in that state raised ``column "embedding" does not exist``.

This reproduces that exact state (table exists, column already
dropped by a later migration) and confirms ``upgrade()`` no longer
errors.
"""

from __future__ import annotations

import os
import uuid

import pytest

from airunner_services.database.session import reset_engine


def _fresh_tenant_key() -> str:
    return f"migtest_f2b3c13e6a1n_{uuid.uuid4().hex[:12]}"


@pytest.fixture()
def _db(monkeypatch: pytest.MonkeyPatch) -> str:
    """Ensure a test database is reachable and initialise the public
    schema. Matches the pattern in test_migration_idempotency.py.

    Does NOT set ``AIRUNNER_DISABLE_DB_SETUP_CACHE`` — see the
    identical comment in ``test_migration_idempotency.py`` for why this
    prevents permanent column-slot exhaustion on
    ``public.pipeline_token_usage``.
    """
    db_url = os.environ.get(
        "AIRUNNER_TEST_DATABASE_URL",
        os.environ.get("AIRUNNER_DATABASE_URL"),
    )
    if not db_url:
        pytest.skip(
            "No test database configured (AIRUNNER_TEST_DATABASE_URL)"
        )
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
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    finally:
        engine.dispose()


def test_upgrade_is_idempotent_after_embedding_column_dropped(
    _db: str,
) -> None:
    """Re-running f2b3c13e6a1n's upgrade() after a later migration has
    already dropped the "embedding" column must not raise."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope

    tenant = _fresh_tenant_key()

    try:
        with tenant_scope(tenant):
            # Materialise the schema — this runs every migration up
            # to and including the latest, so email_body_chunks
            # already has embedding_enc (not embedding) by now.
            with session_scope() as session:
                from airunner_services.database.models.chatstore import (
                    Chatstore,
                )

                session.add(
                    Chatstore(key="mig-f2b3c13e6a1n-test", value={"v": 1})
                )
                session.flush()

            # Re-invoke f2b3c13e6a1n's upgrade() directly against this
            # already-fully-migrated schema, simulating exactly the
            # bug's trigger condition: email_body_chunks exists, but
            # its "embedding" column has already been replaced by
            # "embedding_enc" via f2b3c13e6a1q.
            from alembic import op
            from alembic.runtime.migration import MigrationContext

            with session_scope() as session:
                conn = session.connection()
                ctx = MigrationContext.configure(conn)
                with op.Operations.context(ctx):
                    from airunner_services.database.alembic.versions import (
                        f2b3c13e6a1n_replace_email_thread_summaries_with_body_chunks as migration,
                    )

                    # Must not raise "column embedding does not exist".
                    migration.upgrade()
    finally:
        reset_engine()
        _drop_schema(tenant)
