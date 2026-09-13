"""Add curiosity_data JSONB to chatbots for topic tracking.

Revision ID: be9c1a2d3e68
Revises: be9c1a2d3e67
Create Date: 2026-06-16
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "be9c1a2d3e68"
down_revision: Union[str, None] = "be9c1a2d3e67"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("chatbots", "curiosity_data"):
        op.add_column(
            "chatbots",
            sa.Column("curiosity_data", JSONB, nullable=True),
        )


def downgrade() -> None:
    op.drop_column("chatbots", "curiosity_data")
