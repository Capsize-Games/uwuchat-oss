"""Add uwu_conversations table for UwU-to-UwU DM logs.

Revision ID: be9c1a2d3e65
Revises: be9c1a2d3e64
Create Date: 2026-06-16
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e65"
down_revision: Union[str, None] = "be9c1a2d3e64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create uwu_conversations table."""
    conn = op.get_bind()
    conn.execute(sa.text(
        "CREATE TABLE IF NOT EXISTS uwu_conversations ("
        "  id SERIAL PRIMARY KEY,"
        "  chatbot_a_id INTEGER NOT NULL REFERENCES chatbots(id),"
        "  chatbot_b_id INTEGER NOT NULL REFERENCES chatbots(id),"
        "  messages JSONB NOT NULL DEFAULT '[]'::jsonb,"
        "  last_message_at TIMESTAMP,"
        "  created_at TIMESTAMP,"
        "  updated_at TIMESTAMP,"
        "  is_active BOOLEAN DEFAULT TRUE"
        ")"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_uwu_conversations_a"
        "  ON uwu_conversations(chatbot_a_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_uwu_conversations_b"
        "  ON uwu_conversations(chatbot_b_id)"
    ))


def downgrade() -> None:
    """Drop uwu_conversations table."""
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS uwu_conversations"))
