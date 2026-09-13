"""Add missing BaseModel columns (updated_at, deleted) to items table.

The items table was created before updated_at and deleted were added
to BaseModel, causing INSERT failures in the loot engine.

Revision ID: f2b3c13e6a0p
Revises: f2b3c13e6a0o
Create Date: 2026-06-23
"""

from typing import Union

from alembic import op


revision: str = "f2b3c13e6a0p"
down_revision: Union[str, None] = "f2b3c13e6a0o"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    import sqlalchemy as sa
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("items", "updated_at"):
        op.execute("""
            ALTER TABLE items
            ADD COLUMN updated_at TIMESTAMP
        """)
    if not _column_exists("items", "deleted"):
        op.execute("""
            ALTER TABLE items
            ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT FALSE
        """)


def downgrade() -> None:
    op.execute("ALTER TABLE items DROP COLUMN IF EXISTS deleted")
    op.execute("ALTER TABLE items DROP COLUMN IF EXISTS updated_at")
