"""Add data_source column to knowledge_facts with backfill.

Revision ID: f2b3c13e6a1g
Revises: f2b3c13e6a1f
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1g"
down_revision: Union[str, None] = "f2b3c13e6a1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Return True if *column* already exists on *table*."""
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def _table_has_rows(table: str) -> bool:
    """Return True if *table* has at least one row.

    ``table`` is only ever called with the hardcoded literal
    "knowledge_facts" below -- never user input.
    """
    conn = op.get_bind()
    result = conn.execute(
        sa.text(f"SELECT 1 FROM {table} LIMIT 1")  # nosec B608
    ).scalar()
    return result is not None


def upgrade() -> None:
    if not _column_exists("knowledge_facts", "data_source"):
        op.add_column(
            "knowledge_facts",
            sa.Column(
                "data_source",
                sa.String(32),
                nullable=True,
                index=True,
            ),
        )
    # Backfill existing rows — they all originate from conversations.
    if _table_has_rows("knowledge_facts"):
        op.execute(
            sa.text(
                "UPDATE knowledge_facts "
                "SET data_source = 'conversation' "
                "WHERE data_source IS NULL"
            )
        )


def downgrade() -> None:
    if _column_exists("knowledge_facts", "data_source"):
        op.drop_column("knowledge_facts", "data_source")
