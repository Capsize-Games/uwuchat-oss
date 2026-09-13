"""Reproduce the public.pipeline_token_usage column-churn bug.

Creates N ephemeral tenant schemas in a loop, calling the same
``setup_database`` path that runs on every new user signup.  After each
iteration reports the attnum ceiling on public.pipeline_token_usage.
With the unpatched ``setup_migrations.py``, the count climbs toward
PostgreSQL's 1600-column hard limit with no ceiling (each new tenant
burns 2 attnum slots from the add-then-drop cycle in revisions
f2b3c13e6a0s/t/u + f2b3c13e6a1c).  With the patched code, the count
stays flat because public-schema migrations are not replayed.

Usage (inside the Docker server container):

    python /app/server/tests/repro_column_churn.py
"""

from __future__ import annotations

import os
import sys
import uuid

# Point at the dev database.
os.environ.setdefault(
    "AIRUNNER_DATABASE_URL",
    "postgresql://airunner:airunner@db:5432/airunner",
)
os.environ.setdefault("AIRUNNER_DB_TENANCY", "multi")
os.environ.setdefault("AIRUNNER_DISABLE_DB_SETUP_CACHE", "1")

from sqlalchemy import text

from airunner_services.database.db.engine import create_configured_engine
from airunner_services.database.session import (
    _tenant_db_url,
    reset_engine,
)
from airunner_services.database.setup_database import setup_database
from airunner_services.data.tenant import (
    reset_tenant_key,
    set_tenant_key,
    tenant_schema_for_key,
)


def _public_engine():
    """Return an engine pointed at the public schema."""
    db_url = os.environ["AIRUNNER_DATABASE_URL"]
    return create_configured_engine(
        f"{db_url}?options=-csearch_path=public",
    )


def _column_stats(engine):
    """Return (dropped, max_attnum, live) for public.pipeline_token_usage."""
    with engine.connect() as conn:
        dropped = conn.execute(
            text(
                "SELECT count(*) FILTER (WHERE attisdropped) "
                "FROM pg_attribute "
                "WHERE attrelid = 'public.pipeline_token_usage'::regclass "
                "  AND attnum > 0"
            ),
        ).scalar()
        max_attnum = conn.execute(
            text(
                "SELECT max(attnum) "
                "FROM pg_attribute "
                "WHERE attrelid = 'public.pipeline_token_usage'::regclass "
                "  AND attnum > 0"
            ),
        ).scalar()
        live = conn.execute(
            text(
                "SELECT count(*) FILTER (WHERE NOT attisdropped) "
                "FROM pg_attribute "
                "WHERE attrelid = 'public.pipeline_token_usage'::regclass "
                "  AND attnum > 0"
            ),
        ).scalar()
    return dropped, max_attnum, live


def _drop_schema(schema: str) -> None:
    """Drop an ephemeral tenant schema."""
    engine = _public_engine()
    try:
        with engine.begin() as conn:
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
    finally:
        engine.dispose()


def main() -> None:
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    engine = _public_engine()
    try:
        dropped0, attnum0, live0 = _column_stats(engine)
    finally:
        engine.dispose()

    print(
        f"Start — dropped: {dropped0}, "
        f"max_attnum: {attnum0}, "
        f"live: {live0}",
    )

    db_url = os.environ["AIRUNNER_DATABASE_URL"]
    created_schemas: list[str] = []

    try:
        for i in range(1, iterations + 1):
            tenant_key = f"repro_{uuid.uuid4().hex[:12]}"
            schema = tenant_schema_for_key(tenant_key)
            tenant_url = _tenant_db_url(db_url, schema)

            # Create the PostgreSQL schema.
            base_engine = create_configured_engine(db_url)
            from sqlalchemy.pool import NullPool

            base_engine = create_configured_engine(
                db_url,
                poolclass=NullPool,
            )
            with base_engine.begin() as conn:
                conn.execute(
                    text(f"CREATE SCHEMA IF NOT EXISTS {schema}"),
                )
            base_engine.dispose()

            # Run the full setup_database path — this is what
            # _ensure_tenant_ready calls on every new signup.
            token = set_tenant_key(tenant_key)
            try:
                reset_engine()
                setup_database(db_url=tenant_url)
            except Exception as exc:
                print(f"  [{i}] {schema} FAILED: {exc}")
                _drop_schema(schema)
                continue
            finally:
                reset_tenant_key(token)

            created_schemas.append(schema)

            engine = _public_engine()
            try:
                dropped, attnum, live = _column_stats(engine)
            finally:
                engine.dispose()

            delta_attnum = attnum - attnum0
            print(
                f"  [{i}] {schema[:40]:40s} "
                f"dropped: {dropped:>4d}  "
                f"max_attnum: {attnum:>4d}  "
                f"(+{delta_attnum:>3d})  "
                f"live: {live}",
            )
    finally:
        for schema in created_schemas:
            _drop_schema(schema)

    engine = _public_engine()
    try:
        dropped_final, attnum_final, live_final = _column_stats(engine)
    finally:
        engine.dispose()

    total_delta = attnum_final - attnum0
    print(
        f"\nEnd — dropped: {dropped_final}, "
        f"max_attnum: {attnum_final} "
        f"(+{total_delta} over {iterations} iterations), "
        f"live: {live_final}",
    )
    print(
        "Expected per-iteration burn with unpatched code: "
        "+2 attnum slots",
    )
    print(
        "Expected with patched code: 0 (flat)",
    )
    print(f"Actual burn rate: {total_delta / iterations:.1f} slots/iter")


if __name__ == "__main__":
    main()
