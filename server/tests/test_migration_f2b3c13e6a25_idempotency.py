"""Idempotency test for migration f2b3c13e6a25.

Migration f2b3c13e6a25 adds the composite index
``ix_conversations_chatbot_id_id_desc`` on
``conversations (chatbot_id, id DESC)`` to serve
``SessionManager.load_thread()``.

Confirms that re-running ``upgrade()`` against a public schema that
already has the index does not error, and that the migration's own
``CREATE INDEX`` path still works against a ``conversations`` table
that lacks the index (the production upgrade scenario).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from airunner_services.database.session import reset_engine

INDEX_NAME = "ix_conversations_chatbot_id_id_desc"


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
    """Load migration f2b3c13e6a25 via alembic's ScriptDirectory."""
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
    return script.get_revision("f2b3c13e6a25").module


def _rerun_upgrade() -> None:
    """Re-invoke f2b3c13e6a25's upgrade() against the public schema."""
    from alembic import op
    from alembic.runtime.migration import MigrationContext

    from airunner_services.database.session import public_session_scope

    migration = _load_migration()
    with public_session_scope() as session:
        conn = session.connection()
        ctx = MigrationContext.configure(conn)
        with op.Operations.context(ctx):
            migration.upgrade()


def _conversations_index(inspector, schema: str | None = None):
    """Return the f2b3c13e6a25 index definition, or None."""
    kwargs = {"schema": schema} if schema else {}
    for index in inspector.get_indexes("conversations", **kwargs):
        if index["name"] == INDEX_NAME:
            return index
    return None


def test_upgrade_is_idempotent(_db: str) -> None:
    """Re-running upgrade() on an already-migrated public schema must
    not raise, and the composite DESC index must exist afterwards."""
    from sqlalchemy import inspect

    from airunner_services.database.session import public_session_scope

    _rerun_upgrade()

    with public_session_scope() as session:
        insp = inspect(session.connection())
        index = _conversations_index(insp)
        assert index is not None, (
            f"{INDEX_NAME} must exist on public.conversations"
        )
        assert index["column_names"] == ["chatbot_id", "id"]
        sorting = index.get("column_sorting", {})
        assert sorting.get("id") == ("desc",)

    # Second re-run must also not raise.
    _rerun_upgrade()


def test_upgrade_creates_missing_index(_db: str) -> None:
    """Dropping the index (as on a pre-migration production schema)
    must be repaired by re-running upgrade(); a second re-run must
    no-op."""
    from sqlalchemy import inspect, text

    from airunner_services.database.session import public_session_scope

    with public_session_scope() as session:
        session.execute(
            text(f"DROP INDEX IF EXISTS public.{INDEX_NAME}")
        )
        session.commit()

    _rerun_upgrade()

    with public_session_scope() as session:
        insp = inspect(session.connection())
        index = _conversations_index(insp)
        assert index is not None
        assert index["column_names"] == ["chatbot_id", "id"]
        sorting = index.get("column_sorting", {})
        assert sorting.get("id") == ("desc",)

    # Second re-run with the index present must not raise.
    _rerun_upgrade()
