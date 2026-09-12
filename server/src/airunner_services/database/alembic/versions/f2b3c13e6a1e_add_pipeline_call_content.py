"""Create pipeline_call_content table per tenant schema.

Revision ID: f2b3c13e6a1e
Revises: f2b3c13e6a1d
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1e"
down_revision: Union[str, None] = "f2b3c13e6a1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    """Check whether *table* exists in the current schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names()


def upgrade() -> None:
    """Create pipeline_call_content table if it does not exist."""
    if _table_exists("pipeline_call_content"):
        return

    op.create_table(
        "pipeline_call_content",
        sa.Column(
            "id", sa.Integer(), autoincrement=True, nullable=False,
        ),
        sa.Column("usage_id", sa.Integer(), nullable=False, index=True),
        sa.Column("prompt_text", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_pcc_usage_id", "usage_id"),
    )


def downgrade() -> None:
    """Drop pipeline_call_content table."""
    if not _table_exists("pipeline_call_content"):
        return
    op.drop_table("pipeline_call_content")
