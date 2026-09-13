"""Remove religion JSON from chatbots, scrub belief_tradition from User.data.

Revision ID: f2b3c13e6a20
Revises: f2b3c13e6a19
Create Date: 2026-07-19
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a20"
down_revision: Union[str, None] = "f2b3c13e6a19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def _scrub_belief_tradition() -> None:
    """Remove ``belief_tradition`` key from ``User.data`` rows.

    Uses portable row-by-row Python mutation (same approach for both
    PostgreSQL and SQLite) rather than Postgres-specific JSONB operators,
    since ``User.data`` is ``Column(JSON)`` — plain JSON, not JSONB.
    """
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, data FROM public.users "
            "WHERE data IS NOT NULL"
        )
    ).fetchall()
    for row_id, raw in rows:
        if raw is None:
            continue
        try:
            obj = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(obj, dict):
                continue
            removed = obj.pop("belief_tradition", None)
            if removed is not None:
                conn.execute(
                    sa.text(
                        "UPDATE public.users SET data = :data "
                        "WHERE id = :id"
                    ),
                    {"data": json.dumps(obj), "id": row_id},
                )
        except (json.JSONDecodeError, TypeError):
            pass


def upgrade() -> None:
    """Drop the religion column from chatbots and scrub belief_tradition
    from User.data (a general-purpose JSON blob)."""
    # ── Drop religion column from chatbots ──────────────────────────
    if _column_exists("chatbots", "religion"):
        op.drop_column("chatbots", "religion")

    # ── Scrub belief_tradition key from User.data ───────────────────
    # The User.data column is plain JSON (not JSONB), so we use a
    # portable row-by-row Python approach rather than Postgres-specific
    # jsonb operators like ? and -.
    _scrub_belief_tradition()


def downgrade() -> None:
    """Add the religion column back (no-op for data — we cannot restore
    scrubbed belief_tradition values since they are discarded)."""
    if not _column_exists("chatbots", "religion"):
        op.add_column(
            "chatbots",
            sa.Column("religion", sa.JSON(), nullable=True),
        )
