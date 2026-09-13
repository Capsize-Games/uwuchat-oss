"""Add source_type, source_url, confidence to knowledge_facts.

Revision ID: f2b3c13e6a1f
Revises: f2b3c13e6a19
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1f"
down_revision: Union[str, None] = "f2b3c13e6a1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("knowledge_facts", "source_type"):
        op.add_column(
            "knowledge_facts",
            sa.Column(
                "source_type",
                sa.String(16),
                nullable=False,
                server_default="user_stated",
            ),
        )
    if not _column_exists("knowledge_facts", "source_url"):
        op.add_column(
            "knowledge_facts",
            sa.Column("source_url", sa.String(512), nullable=True),
        )
    if not _column_exists("knowledge_facts", "confidence"):
        op.add_column(
            "knowledge_facts",
            sa.Column("confidence", sa.Float, nullable=True),
        )


def downgrade() -> None:
    if _column_exists("knowledge_facts", "source_type"):
        op.drop_column("knowledge_facts", "source_type")
    if _column_exists("knowledge_facts", "source_url"):
        op.drop_column("knowledge_facts", "source_url")
    if _column_exists("knowledge_facts", "confidence"):
        op.drop_column("knowledge_facts", "confidence")
