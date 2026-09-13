"""Add steam_level column to steam_connections.

Revision ID: f2b3c13e6a12
Revises: f2b3c13e6a11
Create Date: 2026-07-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a12"
down_revision: Union[str, None] = "f2b3c13e6a11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    """Add steam_level column to steam_connections if not present."""
    if not _column_exists("steam_connections", "steam_level"):
        op.add_column(
            "steam_connections",
            sa.Column("steam_level", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    """Remove steam_level column from steam_connections."""
    if _column_exists("steam_connections", "steam_level"):
        op.drop_column("steam_connections", "steam_level")
