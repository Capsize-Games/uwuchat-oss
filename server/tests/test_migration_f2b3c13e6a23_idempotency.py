"""Idempotency test for migration f2b3c13e6a23 (drop Entity.embedding).

Confirms that re-running upgrade() after the embedding column has been
dropped does not error.
"""

from __future__ import annotations

import os
import uuid

import pytest

from airunner_services.database.session import reset_engine


def _fresh_tenant_key() -> str:
    return f"migtest_f2b3c13e6a23_{uuid.uuid4().hex[:12]}"


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
            conn.execute(
                text(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            )
    finally:
        engine.dispose()


def test_upgrade_is_idempotent(_db: str) -> None:
    """Re-running f2b3c13e6a23's upgrade() after the embedding column
    has been dropped must not raise."""
    from airunner_services.data.tenant import tenant_scope
    from airunner_services.database.session import session_scope

    tenant = _fresh_tenant_key()

    try:
        with tenant_scope(tenant):
            with session_scope() as session:
                from airunner_services.database.models.entity import (
                    Entity,
                )

                entity = Entity(
                    entity_type="person",
                    display_name_ct="Test Person",
                    name_lookup_hash="deadbeef",
                )
                session.add(entity)
                session.flush()

        # Second run: reset engine to force re-migration
        reset_engine()

        with tenant_scope(tenant):
            with session_scope() as session:
                from sqlalchemy import inspect

                insp = inspect(session.get_bind())
                cols = [c["name"] for c in insp.get_columns("entities")]
                assert "embedding" not in cols, (
                    "embedding column must not exist after migration"
                )

    finally:
        reset_engine()
        _drop_schema(tenant)
