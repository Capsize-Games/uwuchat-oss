"""Add species_data JSON column to chatbots, migrating existing species values.

Revision ID: be9c1a2d3e62
Revises: be9c1a2d3e61
Create Date: 2026-06-16
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e62"
down_revision: Union[str, None] = "be9c1a2d3e61"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "ALTER TABLE chatbots ADD COLUMN IF NOT EXISTS"
            " species_data JSONB"
        )
    )
    # Migrate existing species string values into the new JSONB column.
    conn.execute(
        sa.text(
            "UPDATE chatbots"
            " SET species_data = jsonb_build_object("
            "   'type', COALESCE(species, 'human'),"
            "   'subtype', NULL,"
            "   'description', NULL"
            " )"
            " WHERE species_data IS NULL"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("ALTER TABLE chatbots DROP COLUMN IF EXISTS species_data")
    )
