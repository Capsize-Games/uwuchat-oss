"""Add profile_url and top_games_json to steam_connections.

Revision ID: f2b3c13e6a14
Revises: f2b3c13e6a13
Create Date: 2026-07-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a14"
down_revision: Union[str, None] = "f2b3c13e6a13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    """Add profile_url and top_games_json columns."""
    for col_name, col_type in (
        ("profile_url", sa.String(512)),
        ("top_games_json", sa.String(4096)),
    ):
        if not _column_exists("steam_connections", col_name):
            op.add_column(
                "steam_connections",
                sa.Column(col_name, col_type, nullable=True),
            )


def downgrade() -> None:
    """Remove profile_url and top_games_json columns."""
    for col_name in ("top_games_json", "profile_url"):
        if _column_exists("steam_connections", col_name):
            op.drop_column("steam_connections", col_name)
