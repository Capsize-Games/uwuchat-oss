"""Create itch_connections table.

Revision ID: f2b3c13e6a16
Revises: f2b3c13e6a15
Create Date: 2026-07-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a16"
down_revision: Union[str, None] = "f2b3c13e6a15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create itch_connections table if it does not exist."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "itch_connections" not in inspector.get_table_names():
        op.create_table(
            "itch_connections",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column(
                "account_id", sa.Integer(), nullable=False, index=True,
                unique=True,
            ),
            sa.Column("itch_user_id", sa.Integer(), nullable=True),
            sa.Column("username", sa.String(255), nullable=True),
            sa.Column("display_name", sa.String(255), nullable=True),
            sa.Column("cover_url", sa.String(512), nullable=True),
            sa.Column("profile_url", sa.String(512), nullable=True),
            sa.Column("owned_games_json", sa.Text(), nullable=True),
            sa.Column("last_scraped_at", sa.DateTime(), nullable=True),
            sa.Column("error", sa.String(512), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(), server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("deleted", sa.Boolean(), server_default=sa.false(),
                      nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    """Drop itch_connections table."""
    op.drop_table("itch_connections")
