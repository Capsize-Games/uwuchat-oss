"""Shared pytest fixtures for eval tests, including ephemeral tenant schemas.

Provides ``ephemeral_tenant`` — a session-scoped fixture that creates a
dedicated PostgreSQL schema (``tenant_scaletest_<uuid>``) with the full
migration/repair path applied, then drops it unconditionally on teardown.

Usage::

    def test_my_scale_case(ephemeral_tenant: str) -> None:
        # *ephemeral_tenant* is the raw tenant key, e.g. "scaletest_abc123".
        # The fixture has already set the :func:`set_tenant_key` contextvar
        # so ORM queries inside this test route to the ephemeral schema.
        ...
"""

from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest
from sqlalchemy import text

from airunner_services.data.tenant import (
    reset_tenant_key,
    set_tenant_key,
    tenant_schema_for_key,
)
from airunner_services.database.db.engine import create_configured_engine
from airunner_services.database.session import (
    _db_url,
    _is_postgres,
    _tenant_db_url,
)
from airunner_services.database.setup_database import setup_database


def _ensure_db_postgres() -> str:
    """Return the database URL, skipping if not PostgreSQL."""
    db_url = _db_url()
    if not _is_postgres(db_url):
        pytest.skip("Scale tests require PostgreSQL with pgvector")
    return db_url


@pytest.fixture(scope="session")
def ephemeral_tenant() -> Generator[str, None, None]:
    """Create and later destroy an ephemeral tenant schema for one test session.

    The schema is fully migrated via :func:`setup_database` so table
    structure (including HNSW indexes) matches production.  On teardown —
    even after a test failure — the schema is unconditionally dropped with
    ``DROP SCHEMA ... CASCADE``, leaving no trace in the persistent dev
    database.
    """
    db_url = _ensure_db_postgres()
    tenant_key = f"scaletest_{uuid.uuid4().hex[:12]}"
    schema_name = tenant_schema_for_key(tenant_key)
    tenant_url = _tenant_db_url(db_url, schema_name)

    # Set the tenant context so that all ORM operations inside the test
    # (via ``session_scope()``) resolve to the ephemeral schema.
    token = set_tenant_key(tenant_key)

    try:
        _create_schema(db_url, schema_name)
        setup_database(db_url=tenant_url)
        yield tenant_key
    finally:
        _destroy_schema(db_url, schema_name)
        reset_tenant_key(token)


def _create_schema(db_url: str, schema_name: str) -> None:
    """Execute ``CREATE SCHEMA IF NOT EXISTS`` on the base database."""
    engine = create_configured_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"),
            )
    finally:
        engine.dispose()


def _destroy_schema(db_url: str, schema_name: str) -> None:
    """Drop *schema_name* with CASCADE, swallowing any errors."""
    engine = create_configured_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"DROP SCHEMA IF EXISTS {schema_name} CASCADE",
                ),
            )
    finally:
        engine.dispose()
