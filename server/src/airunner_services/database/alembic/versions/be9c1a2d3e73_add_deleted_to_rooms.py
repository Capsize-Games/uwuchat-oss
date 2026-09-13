"""Add deleted column to rooms, room_memberships, room_messages.

BaseModel provides a soft-delete 'deleted' column; the original rooms
migration used 'is_active' instead, causing UndefinedColumn errors.

Revision ID: be9c1a2d3e73
Revises: be9c1a2d3e72
Create Date: 2026-06-17
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e73"
down_revision: Union[str, None] = "be9c1a2d3e72"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    for table in ("rooms", "room_memberships", "room_messages"):
        if not _column_exists(table, "deleted"):
            op.execute(
                f"ALTER TABLE {table} "
                f"ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT FALSE"
            )


def downgrade() -> None:
    for table in ("rooms", "room_memberships", "room_messages"):
        if _column_exists(table, "deleted"):
            op.execute(
                f"ALTER TABLE {table} DROP COLUMN deleted"
            )
