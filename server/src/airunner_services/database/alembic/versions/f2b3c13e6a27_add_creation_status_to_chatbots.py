"""Add creation_status to chatbots for durable background creation.

Revision ID: f2b3c13e6a27
Revises: f2b3c13e6a26
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a27"
down_revision: str | None = "f2b3c13e6a26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Values: pending / generating / ready / failed / acknowledged.
# Rows created before this migration never went through a background
# creation job, so their durable state is "ready" (nothing in flight).
# The ``server_default`` both satisfies ``nullable=False`` for rows
# already in the table and backfills them atomically in Postgres.
_READY = "ready"


def _column_exists(table: str, column: str) -> bool:
    """Return whether *column* exists on *table* in the current schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade() -> None:
    """Add ``creation_status`` idempotently, backfilling existing rows."""
    if _column_exists("chatbots", "creation_status"):
        return
    op.add_column(
        "chatbots",
        sa.Column(
            "creation_status",
            sa.String(length=32),
            nullable=False,
            server_default=_READY,
        ),
    )


def downgrade() -> None:
    """Drop ``creation_status`` if present."""
    if _column_exists("chatbots", "creation_status"):
        op.drop_column("chatbots", "creation_status")
