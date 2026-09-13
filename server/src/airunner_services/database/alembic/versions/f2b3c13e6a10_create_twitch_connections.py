"""Create twitch_connections table.

Revision ID: f2b3c13e6a10
Revises: f2b3c13e6a0z
Create Date: 2026-06-30
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a10"
down_revision: Union[str, None] = "f2b3c13e6a0z"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    """Probe whether a table exists in the target schema."""
    inspector = sa.inspect(op.get_bind())
    return table in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("twitch_connections"):
        op.create_table(
            "twitch_connections",
            sa.Column(
                "id", sa.Integer(),
                primary_key=True, autoincrement=True,
            ),
            sa.Column(
                "account_id", sa.Integer(),
                nullable=False, unique=True, index=True,
            ),
            sa.Column(
                "twitch_id", sa.String(64),
                nullable=False, unique=True,
            ),
            sa.Column(
                "display_name", sa.String(255), nullable=True,
            ),
            sa.Column(
                "avatar_url", sa.String(512), nullable=True,
            ),
            sa.Column(
                "email", sa.String(255), nullable=True,
            ),
            sa.Column(
                "description", sa.String(512), nullable=True,
            ),
            sa.Column(
                "last_scraped_at", sa.DateTime(), nullable=True,
            ),
            sa.Column(
                "error", sa.String(512), nullable=True,
            ),
        )


def downgrade() -> None:
    if _table_exists("twitch_connections"):
        op.drop_table("twitch_connections")
