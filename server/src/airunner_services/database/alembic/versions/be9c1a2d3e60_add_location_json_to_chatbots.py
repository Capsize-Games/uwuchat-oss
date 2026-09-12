"""Add location JSON column to chatbots.

Revision ID: be9c1a2d3e60
Revises: be9c1a2d3e59
Create Date: 2026-06-16
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e60"
down_revision: Union[str, None] = "be9c1a2d3e59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "ALTER TABLE chatbots ADD COLUMN IF NOT EXISTS"
            " location JSONB"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("ALTER TABLE chatbots DROP COLUMN IF EXISTS location")
    )
