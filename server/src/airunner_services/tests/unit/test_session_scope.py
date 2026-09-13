"""Tests for multi-tenant session_scope / schema resolution.

These tests verify tenant data isolation — the mechanism the entire
application's data security depends on. They run against a real Postgres
instance because tenant isolation bugs live in ``search_path`` semantics
that mocks cannot catch.

Requires ``AIRUNNER_TEST_DATABASE_URL`` (or ``AIRUNNER_DATABASE_URL``)
pointing to a PostgreSQL instance. Skips gracefully when unavailable.
"""

from __future__ import annotations

import os
import uuid

import pytest

from airunner_services.database.session import (
    reset_engine,
    session_scope,
)
from airunner_services.database.setup_database import setup_database
from airunner_services.data.tenant import (
    set_tenant_key,
    reset_tenant_key,
    tenant_scope,
)

pytestmark = [pytest.mark.functional]


def _fresh_tenant_id() -> str:
    """Return a unique tenant key for an isolated test schema."""
    return f"test-tenant-{uuid.uuid4().hex[:12]}"


def _ensure_db(monkeypatch: pytest.MonkeyPatch) -> str:
    """Configure the test database and initialise the public schema."""
    db_url = os.environ.get(
        "AIRUNNER_TEST_DATABASE_URL",
        os.environ.get("AIRUNNER_DATABASE_URL"),
    )
    if not db_url:
        pytest.skip("No test database configured (AIRUNNER_TEST_DATABASE_URL)")
    if not db_url.startswith("postgres"):
        pytest.skip("Tenant tests require PostgreSQL")
    monkeypatch.setenv("AIRUNNER_DB_TENANCY", "multi")
    monkeypatch.setenv("AIRUNNER_DATABASE_URL", db_url)
    monkeypatch.setenv("AIRUNNER_DISABLE_DB_SETUP_CACHE", "1")
    reset_engine()
    try:
        setup_database()
    except Exception as exc:  # pragma: no cover — env dependent
        pytest.skip(f"Database unavailable: {exc}")
    return db_url


# ---------------------------------------------------------------------------
# Tenant isolation: tenant A cannot read tenant B's data
# ---------------------------------------------------------------------------


def test_tenant_isolation_cannot_read_across_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A session scoped to tenant A cannot read rows from tenant B."""
    _ensure_db(monkeypatch)
    tenant_a = _fresh_tenant_id()
    tenant_b = _fresh_tenant_id()

    # Write a row as tenant A.
    with tenant_scope(tenant_a):
        with session_scope() as session:
            from airunner_services.database.models.chatstore import (
                Chatstore,
            )

            session.add(Chatstore(key="isolation-test", value={"owner": "A"}))
            session.flush()

    # Tenant B must not see tenant A's row.
    with tenant_scope(tenant_b):
        with session_scope() as session:
            from airunner_services.database.models.chatstore import (
                Chatstore,
            )

            rows = (
                session.query(Chatstore)
                .filter(Chatstore.key == "isolation-test")
                .all()
            )
            assert len(rows) == 0, (
                "Tenant B must not see rows from tenant A"
            )

    # Tenant A can still see its own row.
    with tenant_scope(tenant_a):
        with session_scope() as session:
            from airunner_services.database.models.chatstore import (
                Chatstore,
            )

            rows = (
                session.query(Chatstore)
                .filter(Chatstore.key == "isolation-test")
                .all()
            )
            assert len(rows) == 1
            assert rows[0].value == {"owner": "A"}

    # Clean up both schemas afterwards.
    _drop_test_schema(tenant_a)
    _drop_test_schema(tenant_b)


# ---------------------------------------------------------------------------
# Commit persistence: SET LOCAL search_path survives commit
# ---------------------------------------------------------------------------


def test_commit_persistence_across_transactions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Data committed inside session_scope survives for a fresh session.

    Regression test for the "SET LOCAL search_path lost after commit()"
    bug from project memory — a single up-front SET is transaction-scoped
    and discarded by commit(); any statement run afterwards would then hit
    the default ``public`` schema.
    """
    _ensure_db(monkeypatch)
    tenant = _fresh_tenant_id()

    with tenant_scope(tenant):
        with session_scope() as session:
            from airunner_services.database.models.chatstore import (
                Chatstore,
            )

            session.add(Chatstore(key="commit-test", value={"round": 1}))
        # session_scope commits here. A fresh scope must see the row.

        with session_scope() as session:
            from airunner_services.database.models.chatstore import (
                Chatstore,
            )

            row = (
                session.query(Chatstore)
                .filter(Chatstore.key == "commit-test")
                .one_or_none()
            )
            assert row is not None, (
                "Committed row must be visible in a fresh session — "
                "SET LOCAL search_path was likely discarded after commit"
            )
            assert row.value == {"round": 1}

            # Write a second row and verify it is also visible in a third
            # scope — exercises the after_begin listener re-application.
            session.add(Chatstore(key="commit-test-2", value={"round": 2}))

        with session_scope() as session:
            from airunner_services.database.models.chatstore import (
                Chatstore,
            )

            row = (
                session.query(Chatstore)
                .filter(Chatstore.key == "commit-test-2")
                .one_or_none()
            )
            assert row is not None
            assert row.value == {"round": 2}

    _drop_test_schema(tenant)


# ---------------------------------------------------------------------------
# Strict tenant mode: no silent fallback to tenant_anonymous
# ---------------------------------------------------------------------------


def test_strict_tenant_raises_on_missing_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A request with no tenant context raises when STRICT_TENANT is set.

    Regression test for the systemic tenant-context audit finding in
    project memory — unset tenant key silently resolves to
    ``tenant_anonymous`` and writes real data into a bucket no real
    account ever reads.
    """
    _ensure_db(monkeypatch)
    monkeypatch.setenv("AIRUNNER_STRICT_TENANT", "1")

    # Clear any tenant key that may be set by conftest / outer context.
    token = set_tenant_key(None)
    try:
        with pytest.raises(RuntimeError, match="no tenant context"):
            with session_scope():
                pass  # pragma: no cover — the context manager raises
    finally:
        reset_tenant_key(token)

    monkeypatch.delenv("AIRUNNER_STRICT_TENANT", raising=False)


# ---------------------------------------------------------------------------
# New tenant schema creation: tables are materialised
# ---------------------------------------------------------------------------


def test_new_tenant_schema_gets_tables_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A brand-new tenant schema actually gets tables created on first access.

    Regression test for the "tenant data in public schema" bug from
    project memory — ``create_all(checkfirst=True)`` with the default
    ``search_path`` would see public-schema tables and silently skip
    creating the tenant's own copy.
    """
    _ensure_db(monkeypatch)
    tenant = _fresh_tenant_id()

    with tenant_scope(tenant):
        with session_scope() as session:
            # If tables were missing, the write would fail with an
            # "relation does not exist" error — that alone is a useful
            # regression guard. Additionally, verify we can read back.
            from airunner_services.database.models.chatstore import (
                Chatstore,
            )

            session.add(Chatstore(key="schema-test", value={"created": True}))
            session.flush()

    # Verify the table is in the tenant's own schema, not public.
    _assert_table_in_schema("chatstore", tenant)

    _drop_test_schema(tenant)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _drop_test_schema(tenant_key: str) -> None:
    """Drop the schema belonging to *tenant_key* (cleanup)."""
    from airunner_services.data.tenant import tenant_schema_for_key

    schema = tenant_schema_for_key(tenant_key)
    db_url = os.environ.get("AIRUNNER_DATABASE_URL", "")
    if not db_url:
        return

    from airunner_services.database.session import _tenant_db_url

    tenant_url = _tenant_db_url(db_url, schema)
    from airunner_services.database.db.engine import create_configured_engine

    engine = create_configured_engine(tenant_url)
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(
                text(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            )
    finally:
        engine.dispose()


def _assert_table_in_schema(table_name: str, tenant_key: str) -> None:
    """Assert *table_name* exists in the tenant's schema, not public."""
    from airunner_services.data.tenant import tenant_schema_for_key

    schema = tenant_schema_for_key(tenant_key)
    db_url = os.environ.get("AIRUNNER_DATABASE_URL", "")
    if not db_url:
        return

    from airunner_services.database.db.engine import create_configured_engine

    engine = create_configured_engine(db_url)
    try:
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(engine)
        tenant_tables = inspector.get_table_names(schema=schema)
        public_tables = inspector.get_table_names(schema="public")
        assert table_name in tenant_tables, (
            f"Table '{table_name}' must exist in tenant schema '{schema}', "
            f"but only public has: {public_tables}"
        )
    finally:
        engine.dispose()
