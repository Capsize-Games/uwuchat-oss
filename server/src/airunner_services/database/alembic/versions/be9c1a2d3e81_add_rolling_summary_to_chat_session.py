"""add rolling_summary to chat_session

Revision ID: be9c1a2d3e81
Revises: be9c1a2d3e80
Create Date: 2026-06-19
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e81"
down_revision: Union[str, None] = "be9c1a2d3e80"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("chat_sessions", "rolling_summary"):
        op.add_column(
            "chat_sessions",
            sa.Column("rolling_summary", sa.Text, nullable=True),
        )


def downgrade() -> None:
    op.drop_column("chat_sessions", "rolling_summary")
