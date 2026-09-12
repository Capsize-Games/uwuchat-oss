"""Add preferred_language and setup_complete to users.

Revision ID: be9c1a2d3e77
Revises: be9c1a2d3e76
Create Date: 2026-06-17
"""

from alembic import op
import sqlalchemy as sa


revision = "be9c1a2d3e77"
down_revision = "be9c1a2d3e76"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade():
    if not _column_exists("users", "preferred_language"):
        op.add_column(
            "users",
            sa.Column(
                "preferred_language",
                sa.String(),
                nullable=True,
                server_default="en",
            ),
        )
    if not _column_exists("users", "setup_complete"):
        op.add_column(
            "users",
            sa.Column(
                "setup_complete",
                sa.Boolean(),
                nullable=True,
                server_default="false",
            ),
        )


def downgrade():
    pass
