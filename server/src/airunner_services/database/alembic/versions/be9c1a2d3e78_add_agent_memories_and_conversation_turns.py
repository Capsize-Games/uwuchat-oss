"""Add agent_memories and conversation_turns tables.

Revision ID: be9c1a2d3e78
Revises: be9c1a2d3e77
Create Date: 2026-06-19
"""

from alembic import op
import sqlalchemy as sa


revision = "be9c1a2d3e78"
down_revision = "be9c1a2d3e77"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    return table in sa.inspect(conn).get_table_names()


def upgrade():
    if not _table_exists("agent_memories"):
        op.create_table(
            "agent_memories",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "chatbot_id",
                sa.Integer(),
                sa.ForeignKey("chatbots.id"),
                nullable=False,
                unique=True,
                index=True,
            ),
            sa.Column(
                "summary", sa.Text(), nullable=False, server_default=""
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if not _table_exists("conversation_turns"):
        op.create_table(
            "conversation_turns",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "chatbot_id",
                sa.Integer(),
                sa.ForeignKey("chatbots.id"),
                nullable=False,
                index=True,
            ),
            sa.Column("session_id", sa.Integer(), nullable=True, index=True),
            sa.Column(
                "conversation_id",
                sa.Integer(),
                sa.ForeignKey("conversations.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("role", sa.String(16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column(
                "turn_index", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )


def downgrade():
    op.drop_table("conversation_turns")
    op.drop_table("agent_memories")
