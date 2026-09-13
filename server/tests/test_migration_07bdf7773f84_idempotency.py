"""Idempotency test for migration 07bdf7773f84 (code-credits balance).

Confirms that re-running ``upgrade()`` against a public schema that
already has the ``code_credits_usd`` column and the
``code_credit_transactions`` table does not error — the migration
probes column/table existence (``_column_exists`` / ``to_regclass``)
before any DDL, per the repo's migration conventions.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from airunner_services.database.session import reset_engine


@pytest.fixture()
def _db(monkeypatch: pytest.MonkeyPatch) -> str:
    """Ensure a test database is reachable and initialise the public
    schema. Matches the pattern in test_migration_idempotency.py.

    Does NOT set ``AIRUNNER_DISABLE_DB_SETUP_CACHE`` — see the comment
    in ``test_migration_f2b3c13e6a1n_idempotency.py`` for why that
    prevents permanent column-slot exhaustion.
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


def _load_migration():
    """Load migration 07bdf7773f84 via alembic's ScriptDirectory."""
    import importlib

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    # ``import a.b.c as x`` would resolve the re-exported function in the
    # package ``__init__``; importlib always returns the real module.
    setup_db_module = importlib.import_module(
        "airunner_services.database.setup_database"
    )
    alembic_dir = (
        Path(setup_db_module.__file__).resolve().parent / "alembic"
    )
    cfg = Config()
    cfg.set_main_option("script_location", str(alembic_dir))
    script = ScriptDirectory.from_config(cfg)
    return script.get_revision("07bdf7773f84").module


def _rerun_upgrade() -> None:
    """Re-invoke 07bdf7773f84's upgrade() against the public schema."""
    from alembic import op
    from alembic.runtime.migration import MigrationContext

    from airunner_services.database.session import public_session_scope

    migration = _load_migration()
    with public_session_scope() as session:
        conn = session.connection()
        ctx = MigrationContext.configure(conn)
        with op.Operations.context(ctx):
            migration.upgrade()


def test_upgrade_is_idempotent(_db: str) -> None:
    """Re-running upgrade() on an already-migrated public schema must
    not raise, and the column/table must exist afterwards."""
    from sqlalchemy import inspect

    from airunner_services.database.session import public_session_scope

    _rerun_upgrade()

    with public_session_scope() as session:
        insp = inspect(session.connection())
        assert "code_credits_usd" in [
            c["name"] for c in insp.get_columns("accounts")
        ]
        assert "code_credit_transactions" in insp.get_table_names()

    # Second re-run must also not raise.
    _rerun_upgrade()
