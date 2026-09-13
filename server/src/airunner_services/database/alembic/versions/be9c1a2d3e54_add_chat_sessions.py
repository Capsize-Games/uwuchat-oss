"""Add chat_sessions table and session_id to conversations.

Revision ID: be9c1a2d3e54
Revises: be9c1a2d3e53
Create Date: 2026-06-14
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e54"
down_revision: Union[str, None] = "be9c1a2d3e53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── chat_sessions table ────────────────────────────────────────────────
    # to_regclass() is search_path-aware; information_schema with current_schema()
    # only checks the tenant schema and would shadow public.chat_sessions.
    if not conn.execute(
        sa.text("SELECT to_regclass('chat_sessions')")
    ).scalar():
        op.create_table(
            "chat_sessions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("chatbot_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("last_message_at", sa.DateTime(), nullable=False),
            sa.Column("episodic_summary", sa.Text(), nullable=True),
            sa.Column(
                "summary_ready",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column(
                "deleted", sa.Boolean(), nullable=True, server_default="false"
            ),
            sa.ForeignKeyConstraint(
                ["chatbot_id"], ["chatbots.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_chat_sessions_chatbot_id",
            "chat_sessions",
            ["chatbot_id"],
            unique=False,
        )
        op.create_index(
            "ix_chat_sessions_last_message_at",
            "chat_sessions",
            ["last_message_at"],
            unique=False,
        )

    # ── session_id column on conversations ─────────────────────────────────
    conn.execute(
        sa.text(
            "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS session_id INTEGER"
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_conversations_session_id"
            " ON conversations (session_id)"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_conversations_session_id"))
    conn.execute(
        sa.text("ALTER TABLE conversations DROP COLUMN IF EXISTS session_id")
    )
    conn.execute(
        sa.text("DROP INDEX IF EXISTS ix_chat_sessions_last_message_at")
    )
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_chat_sessions_chatbot_id"))
    conn.execute(sa.text("DROP TABLE IF EXISTS chat_sessions"))
