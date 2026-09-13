"""Add emotional_weight and key_topics to chat_sessions.

Revision ID: be9c1a2d3e66
Revises: be9c1a2d3e65
Create Date: 2026-06-16
"""

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "be9c1a2d3e66"
down_revision: Union[str, None] = "be9c1a2d3e65"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("chat_sessions", "emotional_weight"):
        op.add_column(
            "chat_sessions",
            sa.Column("emotional_weight", sa.Float, nullable=True),
        )
    if not _column_exists("chat_sessions", "key_topics"):
        op.add_column(
            "chat_sessions",
            sa.Column("key_topics", JSONB, nullable=True),
        )


def downgrade() -> None:
    op.drop_column("chat_sessions", "key_topics")
    op.drop_column("chat_sessions", "emotional_weight")
