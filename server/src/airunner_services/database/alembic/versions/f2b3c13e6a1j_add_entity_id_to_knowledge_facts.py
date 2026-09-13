"""Add entity_id column to knowledge_facts.

Revision ID: f2b3c13e6a1j
Revises: f2b3c13e6a1i
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1j"
down_revision: Union[str, None] = "f2b3c13e6a1i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Return True if *column* already exists on *table*."""
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("knowledge_facts", "entity_id"):
        op.add_column(
            "knowledge_facts",
            sa.Column("entity_id", sa.Integer, nullable=True),
        )
        op.create_index(
            "ix_knowledge_facts_entity_id",
            "knowledge_facts",
            ["entity_id"],
        )


def downgrade() -> None:
    if _column_exists("knowledge_facts", "entity_id"):
        op.drop_index(
            "ix_knowledge_facts_entity_id",
            table_name="knowledge_facts",
        )
        op.drop_column("knowledge_facts", "entity_id")
