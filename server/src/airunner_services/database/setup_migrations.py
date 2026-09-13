"""Migration-running helpers for setup_database."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

from alembic.config import Config
from alembic import command
from sqlalchemy import inspect, text

from airunner_services.database.db.engine import create_configured_engine
from airunner_services.database.setup_shared import (
    _cached_expected_migration_heads,
    _database_is_at_head,
    _extract_search_path_schema,
)


def _run_migrations(
    alembic_cfg: Config,
    target_db_url: str,
    version_locations: list[Path],
    base: Path,
    db_url: str | None,
) -> bool:
    """Run Alembic migrations and return whether they were applied."""
    if _database_is_at_head(
        alembic_cfg, target_db_url, version_locations, base
    ):
        return False

    # When the target is a tenant schema and the public schema is
    # already at head, skip the full migration replay.  Replaying
    # every revision against a new tenant re-executes public-schema
    # migrations that add/drop columns, burning PostgreSQL attnum
    # slots on each cycle (see f2b3c13e6a0s–f2b3c13e6a1c churn on
    # public.pipeline_token_usage).  _repair_application_schema
    # (called after _run_migrations) creates tenant tables via
    # create_all, so a new tenant gets its full schema without
    # replaying public-scoped revisions.
    #
    # NOTE: a prior revision of this fast path called
    # ``command.upgrade(alembic_cfg, "heads")`` per-tenant here in an
    # attempt to catch intermediate revisions skipped by stamp-only
    # updates. That ran a full Alembic env load/upgrade on every
    # tenant DB session (this function is called from
    # ``_ensure_tenant_ready`` on essentially every request), and this
    # repo's multi-branch revision graph made "heads" ambiguous for
    # tenant schemas, raising ``RevisionError: ... overlaps with
    # other requested revisions ...`` on every call — breaking login
    # and conversation loading outright. Reverted to the cheap
    # stamp-based fast path; keeping migrations that are stamped
    # without running their DDL in sync across tenants is tracked as
    # a follow-up, not solved by running "heads" in the request path.
    target_schema = _extract_search_path_schema(target_db_url)
    if target_schema and target_schema != "public":
        public_url = _build_public_only_db_url(target_db_url)
        if public_url and _database_is_at_head(
            alembic_cfg, public_url, version_locations, base,
        ):
            _stamp_tenant_to_head(
                target_db_url, alembic_cfg, version_locations,
            )
            return False

    _ensure_alembic_version_table(target_db_url)


    old_flag = os.environ.get("AIRUNNER_MIGRATION_RUNNING")
    os.environ["AIRUNNER_MIGRATION_RUNNING"] = "1"

    tenant_token = _set_tenant_for_migration(db_url)
    try:
        command.upgrade(alembic_cfg, "heads")
    finally:
        _restore_tenant_and_flag(tenant_token, old_flag)
    return True


def _ensure_alembic_version_table(target_db_url: str) -> None:
    """Create the alembic_version table in the target schema if absent."""
    target_schema = _extract_search_path_schema(target_db_url)
    if not target_schema:
        return
    schema_engine = create_configured_engine(target_db_url)
    try:
        if "alembic_version" not in inspect(
            schema_engine,
        ).get_table_names(schema=target_schema):
            from sqlalchemy import text as _text

            with schema_engine.begin() as _conn:
                _conn.execute(
                    _text(
                        "CREATE TABLE IF NOT EXISTS "
                        f"{target_schema}.alembic_version "
                        "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                    )
                )
    finally:
        schema_engine.dispose()


def _set_tenant_for_migration(db_url: str | None):
    """Set the tenant key from *db_url* for migration execution."""
    if not db_url:
        return None
    schema = _extract_search_path_schema(db_url)
    if not schema:
        return None
    try:
        from airunner_services.data.tenant import (
            set_tenant_key,
            tenant_key_from_schema,
        )

        raw_tenant = tenant_key_from_schema(schema)
        return set_tenant_key(raw_tenant)
    except Exception:
        return None


def _restore_tenant_and_flag(tenant_token, old_flag) -> None:
    """Restore tenant key and migration flag after upgrade."""
    if tenant_token is not None:
        try:
            from airunner_services.data.tenant import reset_tenant_key

            reset_tenant_key(tenant_token)
        except Exception:
            pass
    if old_flag is None:
        os.environ.pop("AIRUNNER_MIGRATION_RUNNING", None)
    else:
        os.environ["AIRUNNER_MIGRATION_RUNNING"] = old_flag


def _version_locations(base: Path, alembic_dir: Path) -> list[Path]:
    """Return the migration version directories for core."""
    return [alembic_dir / "versions"]


def _gather_tenant_model_classes() -> list:
    """Return all model classes that belong inside the tenant schema."""
    import airunner_services.database.models as model_module

    classes = [
        getattr(model_module, name)
        for name in model_module.__all__
        if hasattr(getattr(model_module, name), "__tablename__")
    ]
    from airunner_services.database.setup_public import (
        _extension_model_classes,
    )

    classes.extend(_extension_model_classes())

    # Project-level models — discovered via import.
    _extend_with_project_models(classes)

    return classes


def _extend_with_project_models(classes: list) -> None:
    """Append the active project's models to the tenant class list.

    Only the active project's models are imported — each project
    defines its own model classes over the same shared headlesscode
    tables, so importing both projects' models in one process would
    raise a SQLAlchemy ``InvalidRequestError`` (duplicate table on one
    MetaData).
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
            f"projects.{project}.server.models"
        )
        names = getattr(mod, "__all__", ())
        for name in names:
            cls = getattr(mod, name)
            if hasattr(cls, "__tablename__"):
                classes.append(cls)
    except ImportError:
        pass


def _materialize_missing_tables(engine, model_classes, target_schema) -> None:
    """Create tables missing from *target_schema* on *engine*."""
    from airunner_services.database.base import Base

    inspector = inspect(engine)
    if target_schema:
        existing = set(inspector.get_table_names(schema=target_schema))
    else:
        existing = set(inspector.get_table_names())
    missing = [
        m.__table__ for m in model_classes if m.__tablename__ not in existing
    ]
    if missing:
        Base.metadata.create_all(bind=engine, tables=missing, checkfirst=False)


def _materialize_missing_columns(
    engine, model_classes, target_schema,
) -> None:
    """Add columns present in the ORM but absent from an existing table.

    This closes the gap left by the stamp-and-skip shortcut in
    ``_run_migrations``: when a tenant already had a table before a
    column-altering migration was authored, the shortcut marks the
    migration as applied without running it, and
    ``_materialize_missing_tables`` skips the table because it
    already exists.  This function inspects every *existing* table
    and issues ``ALTER TABLE … ADD COLUMN …`` for any column the
    ORM expects that is not yet present.

    Queries ``information_schema.columns`` directly — never the
    SQLAlchemy inspector — because the inspector can return cached
    metadata from a previous ``create_all`` call within the same
    engine lifecycle, falsely reporting a fresh table's full column
    set for an old tenant that still has only a subset.
    """
    from sqlalchemy.dialects.postgresql import dialect as pg_dialect

    dialect = pg_dialect()
    seen_tables: set[str] = set()
    for model_cls in model_classes:
        table_name = model_cls.__tablename__
        if table_name in seen_tables:
            continue
        seen_tables.add(table_name)

        db_cols = _get_actual_columns(
            engine, table_name, target_schema,
        )
        if not db_cols:
            continue

        for orm_col in model_cls.__table__.columns:
            if orm_col.key in db_cols:
                continue
            _add_column(
                engine,
                target_schema,
                table_name,
                orm_col,
                dialect,
            )


def _get_actual_columns(
    engine, table_name: str, target_schema: str | None,
) -> set[str]:
    """Return the real column names on *table_name* in *target_schema*.

    Uses ``information_schema.columns`` directly to avoid cached
    inspector metadata (see ``_materialize_missing_columns``).
    """
    if target_schema:
        sql = (
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table "
            "ORDER BY ordinal_position"
        )
        params = {"schema": target_schema, "table": table_name}
    else:
        sql = (
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :table "
            "ORDER BY ordinal_position"
        )
        params = {"table": table_name}
    with engine.begin() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    return {row[0] for row in rows}


def _add_column(
    engine, target_schema, table_name, orm_col, dialect,
) -> None:
    """Add one ORM column to an existing table via raw DDL.

    For non-nullable columns, a DEFAULT clause is required so that
    existing rows can satisfy the constraint.  The DEFAULT value is
    derived from ``server_default`` first (database-level), then
    ``default`` (Python-side), falling back to a type-appropriate
    sentinel when neither is present.
    """
    col_type_sql = orm_col.type.compile(dialect=dialect)
    default_clause = _resolve_default_clause(orm_col)
    if not orm_col.nullable and not default_clause:
        # Non-nullable column with no determinable default — skip.
        # This covers primary-key columns (autoincrement handles
        # those) and any unusual case where the ORM model lacks
        # both server_default and default on a required column.
        return

    nullable = "" if orm_col.nullable else " NOT NULL"
    qualified = (
        f"{target_schema}.{table_name}"
        if target_schema
        else table_name
    )
    ddl = (
        f"ALTER TABLE {qualified} "
        f"ADD COLUMN {orm_col.key} {col_type_sql}"
        f"{nullable}{default_clause}"
    )
    with engine.begin() as conn:
        conn.execute(text(ddl))


def _resolve_default_clause(orm_col) -> str:
    """Return a SQL DEFAULT clause string for *orm_col*, or ''."""
    # Prefer database-level server_default.
    sd = orm_col.server_default
    if sd is not None:
        sd_arg = sd.arg if hasattr(sd, "arg") else sd
        return f" DEFAULT {sd_arg}"
    # Fall back to Python-side default.
    py_default = orm_col.default
    if py_default is not None:
        from sqlalchemy.sql.elements import TextClause

        if callable(py_default.arg):
            # Callables can't be inlined; skip.
            return ""
        raw = py_default.arg
        if isinstance(raw, TextClause):
            return f" DEFAULT {raw.text}"
        if isinstance(raw, str):
            return f" DEFAULT '{raw}'"
        if isinstance(raw, bool):
            return f" DEFAULT {'true' if raw else 'false'}"
        if isinstance(raw, (int, float)):
            return f" DEFAULT {raw}"
        return ""
    return ""


def _repair_application_schema(target_db_url: str) -> None:
    """Ensure core application tables and columns exist in the target
    schema."""
    from airunner_services.database.setup_public import _ensure_startup_rows

    model_classes = _gather_tenant_model_classes()
    target_schema = _extract_search_path_schema(target_db_url)

    engine = create_configured_engine(target_db_url)
    try:
        _materialize_missing_tables(engine, model_classes, target_schema)
        _materialize_missing_columns(engine, model_classes, target_schema)
        _repair_email_message_column_types(engine, target_schema)
        _ensure_startup_rows(engine)
    finally:
        engine.dispose()


def _repair_email_message_column_types(
    engine, target_schema: str | None,
) -> None:
    """Convert email_messages PII columns to TEXT for UserEncryptedText.

    When a tenant schema already has the ``email_messages`` table with
    plaintext column types (VARCHAR / JSONB), the stamp-and-skip
    shortcut in ``_run_migrations`` prevents the Alembic migration
    ``f2b3c13e6a22`` from running.  ``_materialize_missing_columns``
    only adds missing columns — it does not alter types on existing
    ones.  This function closes that gap by applying the same ALTER
    COLUMN TYPE changes the migration would have performed.

    Idempotent — skips columns that are already TEXT.
    """
    table = "email_messages"
    text_columns = [
        "from_address",
        "from_name",
        "to_addresses",
        "cc_addresses",
        "subject",
    ]

    # Probe the real column types in this schema.
    with engine.begin() as conn:
        for col_name in text_columns:
            type_name = _probe_column_type(
                conn, target_schema, table, col_name,
            )
            if type_name is None:
                continue
            if type_name.upper() in ("TEXT",):
                continue
            qualified = (
                f"{target_schema}.{table}"
                if target_schema
                else table
            )
            conn.execute(
                text(
                    f"ALTER TABLE {qualified} "
                    f"ALTER COLUMN {col_name} TYPE TEXT "
                    f"USING {col_name}::text"
                )
            )


def _probe_column_type(
    conn, target_schema: str | None, table: str, column: str,
) -> str | None:
    """Return the data type of one column, or None if absent."""
    if target_schema:
        result = conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_schema = :schema "
                "AND table_name = :table "
                "AND column_name = :column"
            ),
            {"schema": target_schema, "table": table, "column": column},
        ).scalar()
    else:
        result = conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = :table "
                "AND column_name = :column"
            ),
            {"table": table, "column": column},
        ).scalar()
    return result


def _append_extension_migration_paths(
    version_locations: list[Path],
) -> None:
    """Append extension Alembic version directories."""
    from airunner_services.extensions.loader import (
        get_extension_migration_paths,
    )

    for ext_path in get_extension_migration_paths():
        versions_dir = ext_path / "versions"
        if versions_dir.is_dir():
            version_locations.append(versions_dir)


def _build_public_only_db_url(tenant_db_url: str) -> str | None:
    """Return a DB URL whose search_path is ``public`` only."""
    try:
        from sqlalchemy.engine import make_url
        from sqlalchemy.engine.url import URL

        url = make_url(tenant_db_url)
        query = dict(url.query or {})
        query["options"] = "-csearch_path=public"
        new_url = URL.create(
            drivername=url.drivername,
            username=url.username,
            password=url.password,
            host=url.host,
            port=url.port,
            database=url.database,
            query=query,
        )
        return new_url.render_as_string(hide_password=False)
    except Exception:
        return None


def _stamp_tenant_to_head(
    target_db_url: str,
    alembic_cfg: Config,
    version_locations: list[Path],
) -> None:
    """Mark every expected migration head as applied in the tenant
    schema so Alembic considers it up-to-date without replaying
    public-schema revisions."""

    target_schema = _extract_search_path_schema(target_db_url)
    if not target_schema:
        return

    # Resolve expected heads from disk.
    base = Path(os.path.dirname(os.path.realpath(__file__)))
    heads = _cached_expected_migration_heads(
        alembic_cfg, version_locations, base,
    )
    if not heads:
        return

    schema_engine = create_configured_engine(target_db_url)
    try:
        if "alembic_version" not in inspect(
            schema_engine,
        ).get_table_names(schema=target_schema):
            with schema_engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS "
                        f"{target_schema}.alembic_version "
                        "(version_num VARCHAR(32) "
                        "NOT NULL PRIMARY KEY)"
                    )
                )
        with schema_engine.begin() as conn:
            for head in heads:
                conn.execute(
                    text(
                        f"INSERT INTO {target_schema}.alembic_version "
                        "(version_num) VALUES (:head) "
                        "ON CONFLICT (version_num) DO NOTHING"
                    ),
                    {"head": head},
                )
    finally:
        schema_engine.dispose()
