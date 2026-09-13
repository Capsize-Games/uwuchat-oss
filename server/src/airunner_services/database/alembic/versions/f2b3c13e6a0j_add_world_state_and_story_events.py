"""Add world_state, voice_samples to chatbots and chatbot_story_events table.

Revision ID: f2b3c13e6a0j
Revises: f2b3c13e6a0i
Create Date: 2026-06-21 19:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from typing import Sequence, Union

revision: str = "f2b3c13e6a0j"
down_revision: Union[str, None] = "f2b3c13e6a0i"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    return table in sa.inspect(conn).get_table_names()


def upgrade() -> None:
    """Add world_state, voice_samples to chatbots; create story events."""
    if not _column_exists("chatbots", "world_state"):
        op.add_column(
            "chatbots",
            sa.Column("world_state", sa.JSON(), nullable=True),
        )
    if not _column_exists("chatbots", "voice_samples"):
        op.add_column(
            "chatbots",
            sa.Column("voice_samples", sa.JSON(), nullable=True),
        )
    if not _column_exists("users", "streak_count"):
        op.add_column(
            "users",
            sa.Column(
                "streak_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if not _column_exists("users", "streak_last_date"):
        op.add_column(
            "users",
            sa.Column(
                "streak_last_date",
                sa.Date(),
                nullable=True,
            ),
        )
    if not _table_exists("chatbot_story_events"):
        op.create_table(
            "chatbot_story_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "chatbot_id",
                sa.Integer(),
                sa.ForeignKey("chatbots.id"),
                nullable=False,
            ),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column(
                "occurred_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "surfaced",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column(
                "deleted",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )


def downgrade() -> None:
    """Remove progression columns and story events table."""
    op.drop_column("users", "streak_last_date")
    op.drop_column("users", "streak_count")
    op.drop_column("chatbots", "voice_samples")
    op.drop_column("chatbots", "world_state")
    op.drop_table("chatbot_story_events")
