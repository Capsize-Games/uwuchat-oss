"""Rebuild pipeline_token_usage to reclaim dropped-column attnum slots.

Revision ID: f2b3c13e6a1s
Revises: f2b3c13e6a1n
Create Date: 2026-07-22

The table hit PostgreSQL's 1600-column hard ceiling after ~1 574
add-then-drop cycles from repeated migration-test runs against the
shared public schema.  This migration rebuilds the table via
CREATE TABLE ... LIKE / INSERT INTO SELECT / RENAME / DROP, which
compacts the physical columns and reclaims all attnum slots so
future ADD COLUMN operations succeed.

Safe to re-run: queries ``pg_attribute`` for dropped columns before
acting.  A table with zero dropped columns is already rebuilt (or
was never damaged) and is skipped.

Index names are preserved: ``LIKE INCLUDING ALL`` copies indexes
but names them after the new table (``pipeline_token_usage_new_*``).
After the swap, every index is renamed back to its original name
by matching column lists against the saved originals.
"""

from __future__ import annotations

from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2b3c13e6a1s"
down_revision: Union[str, None] = "f2b3c13e6a1n"
branch_labels = None
depends_on = None

_TABLE = "public.pipeline_token_usage"
_SEQUENCE = "public.pipeline_token_usage_id_seq"
_OLD = "public.pipeline_token_usage_old"
_NEW = "public.pipeline_token_usage_new"

# Unqualified names for pg_attribute / pg_index lookups.
_TABLE_BARE = "pipeline_token_usage"
_OLD_BARE = "pipeline_token_usage_old"
_NEW_BARE = "pipeline_token_usage_new"


def _table_exists(qualified_name: str) -> bool:
    """Return True when *qualified_name* exists in the public schema."""
    bare = qualified_name.split(".")[-1]
    return bare in sa.inspect(op.get_bind()).get_table_names(
        schema="public",
    )


def _dropped_column_count(table: str) -> int:
    """Return the number of dropped (attisdropped) columns on *table*.

    Returns 0 when the table does not exist.
    """
    conn = op.get_bind()
    try:
        result = conn.execute(
            sa.text(
                "SELECT count(*) FILTER (WHERE attisdropped) AS dropped "
                "FROM pg_attribute "
                "WHERE attrelid = :tbl ::regclass AND attnum > 0"
            ),
            {"tbl": table},
        )
        return int(result.scalar() or 0)
    except Exception:
        return 0


def _capture_original_indexes(
    conn, qualified_table: str,
) -> list[tuple[str, list[str]]]:
    """Return ``(indexname, [columns])`` for every index on *table*.

    Captured before the rebuild so names can be restored afterward.
    """
    result = conn.execute(
        sa.text(
            "SELECT c.relname AS indexname, "
            "       array_agg(a.attname ORDER BY a.attnum) "
            "FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_attribute a "
            "  ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = :tbl ::regclass "
            "GROUP BY c.relname"
        ),
        {"tbl": qualified_table},
    )
    return [(row[0], row[1]) for row in result.fetchall()]


def _restore_index_names(
    conn, orig_idxs: list[tuple[str, list[str]]],
) -> None:
    """Rename every index on ``_TABLE`` whose name contains ``_new``
    back to its original name.

    Matches by indexed-column list rather than by name or position.
    """
    current = conn.execute(
        sa.text(
            "SELECT c.relname AS indexname, "
            "       array_agg(a.attname ORDER BY a.attnum) "
            "FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "JOIN pg_attribute a "
            "  ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) "
            "WHERE i.indrelid = :tbl ::regclass "
            "  AND c.relname LIKE :pat "
            "GROUP BY c.relname"
        ),
        {"tbl": _TABLE, "pat": f"%{_NEW_BARE}%"},
    ).fetchall()

    for cur_name, cur_cols in current:
        for orig_name, orig_cols in orig_idxs:
            if cur_cols == orig_cols:
                conn.execute(
                    sa.text(
                        f"ALTER INDEX {cur_name} RENAME TO {orig_name}"
                    )
                )
                break


def _finish_rebuild(conn) -> None:
    """Complete a partially-applied rebuild."""
    if _table_exists(_NEW):
        # See the matching comment in upgrade() — empty-table-safe
        # setval, avoids NumericValueOutOfRange against MINVALUE 1.
        op.execute(
            sa.text(
                f"SELECT setval('{_SEQUENCE}', "
                f"COALESCE((SELECT MAX(id) FROM {_NEW}), 1), "
                f"(SELECT MAX(id) FROM {_NEW}) IS NOT NULL)"
            )
        )
        op.execute(
            sa.text(f"ALTER SEQUENCE {_SEQUENCE} OWNED BY {_NEW}.id")
        )
        op.execute(sa.text(f"ALTER TABLE {_NEW} RENAME TO {_TABLE_BARE}"))
        if _table_exists(_OLD):
            orig_idxs = _capture_original_indexes(conn, _OLD)
            op.execute(sa.text(f"DROP TABLE {_OLD}"))
            _restore_index_names(conn, orig_idxs)
        return

    if _table_exists(_OLD):
        op.execute(sa.text(f"DROP TABLE {_OLD}"))


def upgrade() -> None:
    """Rebuild pipeline_token_usage to compact its physical columns."""
    conn = op.get_bind()

    if _table_exists(_OLD):
        _finish_rebuild(conn)
        return

    if not _table_exists(_TABLE):
        return

    dropped = _dropped_column_count(_TABLE)
    if dropped == 0:
        return

    orig_idxs = _capture_original_indexes(conn, _TABLE)

    # 1. Create new table with same structure.
    op.execute(
        sa.text(f"CREATE TABLE {_NEW} (LIKE {_TABLE} INCLUDING ALL)")
    )

    # 2. Copy all data.
    op.execute(sa.text(f"INSERT INTO {_NEW} SELECT * FROM {_TABLE}"))

    # 3. Fix sequence ownership BEFORE dropping old table.
    # On a truly empty table (e.g. a fresh database that has never
    # inserted a row into this table), COALESCE(MAX(id), 0) yields 0,
    # and setval(seq, 0) is rejected by Postgres for any sequence with
    # the default MINVALUE of 1. Use the standard empty-table-safe
    # idiom instead: fall back to 1 with is_called=false, so the next
    # nextval() correctly returns 1 rather than erroring or skipping
    # the first value.
    op.execute(
        sa.text(
            f"SELECT setval('{_SEQUENCE}', "
            f"COALESCE((SELECT MAX(id) FROM {_NEW}), 1), "
            f"(SELECT MAX(id) FROM {_NEW}) IS NOT NULL)"
        )
    )
    op.execute(
        sa.text(f"ALTER SEQUENCE {_SEQUENCE} OWNED BY {_NEW}.id")
    )

    # 4. Swap tables — RENAME TO takes a bare name, not schema-qualified.
    op.execute(sa.text(f"ALTER TABLE {_TABLE} RENAME TO {_OLD_BARE}"))
    op.execute(sa.text(f"ALTER TABLE {_NEW} RENAME TO {_TABLE_BARE}"))

    # 5. Drop old table first — its indexes would conflict with
    #    the rename in step 6 if they share names.
    op.execute(sa.text(f"DROP TABLE {_OLD}"))

    # 6. Restore original index names (safe now: old table gone).
    _restore_index_names(conn, orig_idxs)


def downgrade() -> None:
    """This migration is not reversible — it compacts columns but
    does not change the logical schema."""
    pass
