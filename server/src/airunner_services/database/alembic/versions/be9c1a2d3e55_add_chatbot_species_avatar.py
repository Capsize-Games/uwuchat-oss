"""Add species and avatar_emoji columns to chatbots.

Revision ID: be9c1a2d3e55
Revises: be9c1a2d3e54
Create Date: 2026-06-14
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e55"
down_revision: Union[str, None] = "be9c1a2d3e54"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    for col_name in ("species", "avatar_emoji"):
        conn.execute(
            sa.text(
                f"ALTER TABLE chatbots ADD COLUMN IF NOT EXISTS {col_name} TEXT"
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE chatbots DROP COLUMN IF EXISTS species"))
    conn.execute(
        sa.text("ALTER TABLE chatbots DROP COLUMN IF EXISTS avatar_emoji")
    )
