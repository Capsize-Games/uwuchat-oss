"""Add updated_at and deleted columns to world_events.

BaseModel provides soft-delete and auto-timestamp columns; the original
world_events migration was created before those were on BaseModel, so the
table is missing ``updated_at`` and ``deleted``.

Revision ID: be9c1a2d3e79
Revises: be9c1a2d3e78
Create Date: 2026-06-19
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e79"
down_revision: Union[str, None] = "be9c1a2d3e78"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("world_events", "updated_at"):
        op.execute(
            "ALTER TABLE world_events "
            "ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT NOW()"
        )
    if not _column_exists("world_events", "deleted"):
        op.execute(
            "ALTER TABLE world_events "
            "ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT FALSE"
        )


def downgrade() -> None:
    if _column_exists("world_events", "updated_at"):
        op.execute(
            "ALTER TABLE world_events DROP COLUMN updated_at"
        )
    if _column_exists("world_events", "deleted"):
        op.execute(
            "ALTER TABLE world_events DROP COLUMN deleted"
        )
