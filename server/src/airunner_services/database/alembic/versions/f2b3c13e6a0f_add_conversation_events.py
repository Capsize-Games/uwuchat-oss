"""Add immutable conversation_events table.

Revision ID: f2b3c13e6a0f
Revises: be9c1a2d3e87
Create Date: 2026-06-21 14:09:20.913267
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f2b3c13e6a0f"
down_revision: Union[str, None] = "be9c1a2d3e87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create conversation_events table if it does not exist."""
    conn = op.get_bind()
    conn.execute(sa.text(
        "CREATE TABLE IF NOT EXISTS conversation_events ("
        "  id BIGSERIAL PRIMARY KEY,"
        "  event_id UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,"
        "  chatbot_id INTEGER NOT NULL,"
        "  conversation_id INTEGER REFERENCES conversations(id)"
        "    ON DELETE SET NULL,"
        "  session_id INTEGER REFERENCES chat_sessions(id)"
        "    ON DELETE SET NULL,"
        "  event_type TEXT NOT NULL,"
        "  actor TEXT NOT NULL,"
        "  actor_user_id INTEGER,"
        "  payload JSONB NOT NULL,"
        "  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
        "  sequence_num INTEGER"
        ")"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_conversation_events_chatbot_created"
        "  ON conversation_events (chatbot_id, created_at)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_conversation_events_conversation"
        "  ON conversation_events (conversation_id)"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_conversation_events_event_type"
        "  ON conversation_events (event_type)"
    ))


def downgrade() -> None:
    """Drop conversation_events table."""
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS conversation_events"))
