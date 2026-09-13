"""Public schema table setup helpers for multi-tenant mode."""

from __future__ import annotations

import importlib
import os

from sqlalchemy.orm import sessionmaker


def _env_is_truthy(name: str) -> bool:
    return (os.environ.get(name, "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _extension_model_classes() -> list:
    """Return extension models that should be created in the target schema."""
    from airunner_services.extensions.loader import (
        get_extension_models,
    )

    return [
        m
        for m in get_extension_models()
        if not getattr(m, "__public_schema__", False)
    ]


def _extension_public_model_classes() -> list:
    """Return extension models that belong in the **public** schema."""
    from airunner_services.extensions.loader import (
        get_extension_models,
    )

    return [
        m
        for m in get_extension_models()
        if getattr(m, "__public_schema__", False)
    ]


def _repair_account_columns(target_db_url: str) -> None:
    """Add missing columns to the ``accounts`` table (public schema).

    Called after migrations on every startup so column additions that
    can't go through Alembic (revision ID conflicts) are still applied.
    Idempotent — skips columns that already exist.
    """
    from airunner_services.database.db.engine import create_configured_engine
    from sqlalchemy import inspect as sa_inspect, text

    engine = create_configured_engine(target_db_url)
    try:
        inspector = sa_inspect(engine)
        existing = {
            col["name"] for col in inspector.get_columns("accounts")
        }
        if "is_suspended" not in existing:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE accounts "
                        "ADD COLUMN is_suspended BOOLEAN "
                        "NOT NULL DEFAULT false"
                    )
                )
        if "steam_id" not in existing:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE accounts "
                        "ADD COLUMN steam_id VARCHAR NULL"
                    )
                )
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS "
                        "ix_accounts_steam_id ON accounts (steam_id)"
                    )
                )
        if "twitch_id" not in existing:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE accounts "
                        "ADD COLUMN twitch_id VARCHAR NULL"
                    )
                )
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS "
                        "ix_accounts_twitch_id ON accounts (twitch_id)"
                    )
                )
    finally:
        engine.dispose()


def _setup_public_schema_tables(target_db_url: str) -> None:
    """Create extension tables that belong to the **public** schema."""
    import sqlalchemy as sa
    from airunner_services.database.base import Base

    models = _extension_public_model_classes()
    if not models:
        return
    from airunner_services.database.db.engine import create_configured_engine

    engine = create_configured_engine(target_db_url)
    try:
        existing = set(sa.inspect(engine).get_table_names())
        missing = [
            m.__table__ for m in models if m.__tablename__ not in existing
        ]
        if missing:
            Base.metadata.create_all(
                bind=engine,
                tables=missing,
                checkfirst=True,
            )
    finally:
        engine.dispose()


def _core_startup_models() -> tuple[type[object], ...]:
    """Return singleton models required for safe GUI startup."""
    from airunner_services.database.models.application_settings import (
        ApplicationSettings,
    )
    from airunner_services.database.models.path_settings import PathSettings

    return (PathSettings, ApplicationSettings)


def _ensure_project_system_bots(session) -> None:
    """Delegate system-bot seeding to the active project, if any.

    Only the active project's seed module is imported — each project
    defines its own model classes over the same shared tables (e.g.
    ``headlesscode_projects``), so importing both projects' models in
    one process would raise a SQLAlchemy ``InvalidRequestError``.
    """
    project = os.environ.get("AIRUNNER_PROJECT", "")
    try:
        from airunner_services.conf import settings

        project = project or (getattr(settings, "AIRUNNER_PROJECT", "") or "")
    except Exception:
        pass
    if not project:
        return
    try:
        mod = importlib.import_module(
            f"projects.{project}.server.seed"
        )
        mod.ensure_system_bot(session)
    except ImportError:
        pass


def _ensure_startup_rows(engine) -> None:
    """Create default singleton rows required during startup."""
    Session = sessionmaker(bind=engine)
    with Session() as session:
        created = False
        for model in _core_startup_models():
            if session.query(model).first() is None:
                session.add(model())
                created = True
        if created:
            session.commit()
        _ensure_project_system_bots(session)
