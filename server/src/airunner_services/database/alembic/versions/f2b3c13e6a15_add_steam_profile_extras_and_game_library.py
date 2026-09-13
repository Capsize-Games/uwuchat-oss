"""Add persona_state, time fields, full game library, and recently played to steam_connections.

Revision ID: f2b3c13e6a15
Revises: f2b3c13e6a14
Create Date: 2026-07-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a15"
down_revision: Union[str, None] = "f2b3c13e6a14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    """Add persona/time columns and game-library JSON columns."""
    additions: list[tuple[str, type[sa.types.TypeEngine]]] = [
        ("persona_state", sa.Integer),
        ("last_logoff", sa.DateTime),
        ("time_created", sa.DateTime),
        ("all_games_json", sa.Text),
        ("recently_played_json", sa.Text),
    ]
    for col_name, col_type in additions:
        if not _column_exists("steam_connections", col_name):
            op.add_column(
                "steam_connections",
                sa.Column(col_name, col_type, nullable=True),
            )

    # Widen top_games_json from String to Text if needed
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    for col in inspector.get_columns("steam_connections"):
        if col["name"] == "top_games_json":
            if isinstance(col["type"], sa.String):
                op.alter_column(
                    "steam_connections",
                    "top_games_json",
                    existing_type=sa.String(4096),
                    type_=sa.Text(),
                    existing_nullable=True,
                )
            break


def downgrade() -> None:
    """Remove new columns and revert top_games_json to String."""
    for col_name in (
        "recently_played_json",
        "all_games_json",
        "time_created",
        "last_logoff",
        "persona_state",
    ):
        if _column_exists("steam_connections", col_name):
            op.drop_column("steam_connections", col_name)

    conn = op.get_bind()
    inspector = sa.inspect(conn)
    for col in inspector.get_columns("steam_connections"):
        if col["name"] == "top_games_json":
            if isinstance(col["type"], sa.Text):
                op.alter_column(
                    "steam_connections",
                    "top_games_json",
                    existing_type=sa.Text(),
                    type_=sa.String(4096),
                    existing_nullable=True,
                )
            break
