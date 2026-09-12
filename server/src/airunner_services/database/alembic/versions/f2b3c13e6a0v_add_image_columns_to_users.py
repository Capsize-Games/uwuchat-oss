"""add avatar_image and banner_image to users

Revision ID: f2b3c13e6a0v
Revises: f2b3c13e6a0u
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa


revision = "f2b3c13e6a0v"
down_revision = "f2b3c13e6a0u"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("users", "avatar_image"):
        op.add_column(
            "users",
            sa.Column("avatar_image", sa.Text, nullable=True),
        )
    if not _column_exists("users", "banner_image"):
        op.add_column(
            "users",
            sa.Column("banner_image", sa.Text, nullable=True),
        )


def downgrade() -> None:
    op.drop_column("users", "banner_image")
    op.drop_column("users", "avatar_image")
