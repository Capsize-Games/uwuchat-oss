"""Add total_games_owned, total_playtime_minutes, friend_count to steam_connections.

Revision ID: f2b3c13e6a13
Revises: f2b3c13e6a12
Create Date: 2026-07-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a13"
down_revision: Union[str, None] = "f2b3c13e6a12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    """Add stats columns to steam_connections."""
    for col_name in (
        "total_games_owned",
        "total_playtime_minutes",
        "friend_count",
    ):
        if not _column_exists("steam_connections", col_name):
            op.add_column(
                "steam_connections",
                sa.Column(col_name, sa.Integer(), nullable=True),
            )


def downgrade() -> None:
    """Remove stats columns from steam_connections."""
    for col_name in (
        "friend_count",
        "total_playtime_minutes",
        "total_games_owned",
    ):
        if _column_exists("steam_connections", col_name):
            op.drop_column("steam_connections", col_name)
