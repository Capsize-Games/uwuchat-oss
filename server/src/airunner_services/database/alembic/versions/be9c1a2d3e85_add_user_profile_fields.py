"""Add display_name, gender, daily_gems_claimed_at to users.

Supports the setup funnel (name/gender) and the daily gem bonus.

Revision ID: be9c1a2d3e85
Revises: be9c1a2d3e84
Create Date: 2026-06-20
"""

from alembic import op
import sqlalchemy as sa


revision = "be9c1a2d3e85"
down_revision = "be9c1a2d3e84"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [c["name"] for c in sa.inspect(conn).get_columns(table)]
    return column in cols


def upgrade():
    if not _column_exists("users", "display_name"):
        op.add_column(
            "users",
            sa.Column("display_name", sa.String(100), nullable=True),
        )
    if not _column_exists("users", "gender"):
        op.add_column(
            "users",
            sa.Column("gender", sa.String(20), nullable=True),
        )
    if not _column_exists("users", "daily_gems_claimed_at"):
        op.add_column(
            "users",
            sa.Column(
                "daily_gems_claimed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade():
    op.drop_column("users", "daily_gems_claimed_at")
    op.drop_column("users", "gender")
    op.drop_column("users", "display_name")
