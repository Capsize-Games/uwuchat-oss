"""add avatar_image and banner_image to chatbots

Revision ID: be9c1a2d3e76
Revises: be9c1a2d3e75
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa


revision = "be9c1a2d3e76"
down_revision = "be9c1a2d3e75"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("chatbots", "avatar_image"):
        op.add_column(
            "chatbots",
            sa.Column("avatar_image", sa.Text, nullable=True),
        )
    if not _column_exists("chatbots", "banner_image"):
        op.add_column(
            "chatbots",
            sa.Column("banner_image", sa.Text, nullable=True),
        )


def downgrade() -> None:
    op.drop_column("chatbots", "banner_image")
    op.drop_column("chatbots", "avatar_image")
