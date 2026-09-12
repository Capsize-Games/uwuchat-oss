"""Add achievements_cache_json to steam_connections.

Revision ID: f2b3c13e6a19
Revises: f2b3c13e6a18
Create Date: 2026-07-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a19"
down_revision: Union[str, None] = "f2b3c13e6a18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    """Add achievements_cache_json column."""
    if not _column_exists(
        "steam_connections", "achievements_cache_json",
    ):
        op.add_column(
            "steam_connections",
            sa.Column(
                "achievements_cache_json",
                sa.Text(),
                nullable=True,
            ),
        )


def downgrade() -> None:
    """Remove achievements_cache_json column."""
    if _column_exists(
        "steam_connections", "achievements_cache_json",
    ):
        op.drop_column(
            "steam_connections", "achievements_cache_json",
        )
