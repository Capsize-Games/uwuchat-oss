"""Add religion JSON column to chatbots.

Revision ID: be9c1a2d3e8a
Revises: be9c1a2d3e89
Create Date: 2026-07-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e8a"
down_revision: Union[str, None] = "be9c1a2d3e89"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    """Add religion with a default of NULL."""
    if not _column_exists("chatbots", "religion"):
        op.add_column(
            "chatbots",
            sa.Column("religion", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    """Remove religion column."""
    op.drop_column("chatbots", "religion")
