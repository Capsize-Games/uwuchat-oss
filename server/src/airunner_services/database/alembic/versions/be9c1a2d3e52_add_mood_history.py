"""Add mood_history table for per-turn chatbot mood tracking.

Revision ID: be9c1a2d3e52
Revises: be9c1a2d3e51
Create Date: 2026-06-14 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e52"
down_revision: Union[str, None] = "be9c1a2d3e51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # to_regclass() resolves the name via search_path, so it finds public.mood_history
    # when running against a tenant URL. CREATE TABLE IF NOT EXISTS only checks
    # the current (tenant) schema and would create a shadowing empty copy.
    if not conn.execute(
        sa.text("SELECT to_regclass('mood_history')")
    ).scalar():
        op.create_table(
            "mood_history",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("chatbot_id", sa.Integer(), nullable=True),
            sa.Column("conversation_id", sa.Integer(), nullable=True),
            sa.Column(
                "mood", sa.String(64), nullable=False, server_default=""
            ),
            sa.Column(
                "emoji", sa.String(16), nullable=False, server_default=""
            ),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column(
                "intensity", sa.Float(), nullable=False, server_default="0.5"
            ),
            sa.Column("deleted", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_mood_history_chatbot_id", "mood_history", ["chatbot_id"]
        )
        op.create_index(
            "ix_mood_history_conversation_id",
            "mood_history",
            ["conversation_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_mood_history_conversation_id", table_name="mood_history")
    op.drop_index("ix_mood_history_chatbot_id", table_name="mood_history")
    op.drop_table("mood_history")
