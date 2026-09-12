"""Add attributes JSON column to chatbots.

Revision ID: be9c1a2d3e58
Revises: be9c1a2d3e57
Create Date: 2026-06-15
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e58"
down_revision: Union[str, None] = "be9c1a2d3e57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "ALTER TABLE chatbots ADD COLUMN IF NOT EXISTS"
            " attributes JSONB"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("ALTER TABLE chatbots DROP COLUMN IF EXISTS attributes")
    )
