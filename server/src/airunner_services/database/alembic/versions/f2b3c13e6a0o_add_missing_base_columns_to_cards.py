"""Add missing BaseModel columns (updated_at, deleted) to cards table.

The original cards migration omitted these, causing INSERT failures.

Revision ID: f2b3c13e6a0o
Revises: f2b3c13e6a0n
Create Date: 2026-06-22
"""

from typing import Union

from alembic import op


revision: str = "f2b3c13e6a0o"
down_revision: Union[str, None] = "f2b3c13e6a0n"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    import sqlalchemy as sa
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("cards", "updated_at"):
        op.execute("""
            ALTER TABLE cards
            ADD COLUMN updated_at TIMESTAMP
        """)
    if not _column_exists("cards", "deleted"):
        op.execute("""
            ALTER TABLE cards
            ADD COLUMN deleted BOOLEAN NOT NULL DEFAULT FALSE
        """)


def downgrade() -> None:
    op.execute("ALTER TABLE cards DROP COLUMN IF EXISTS deleted")
    op.execute("ALTER TABLE cards DROP COLUMN IF EXISTS updated_at")
