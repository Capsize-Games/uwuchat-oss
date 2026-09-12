"""Add relationships table for chatbot social graph.

Revision ID: be9c1a2d3e67
Revises: be9c1a2d3e66
Create Date: 2026-06-16
"""

from typing import Union

from alembic import op

revision: str = "be9c1a2d3e67"
down_revision: Union[str, None] = "be9c1a2d3e66"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id SERIAL PRIMARY KEY,
            chatbot_id INTEGER REFERENCES chatbots(id) ON DELETE CASCADE,
            target_type VARCHAR(16) NOT NULL,
            target_id INTEGER NOT NULL,
            warmth FLOAT NOT NULL DEFAULT 0.5,
            trust FLOAT NOT NULL DEFAULT 0.5,
            dynamic VARCHAR(64),
            private_thoughts TEXT,
            last_interaction_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        uq_relationships_chatbot_target
        ON relationships (chatbot_id, target_type, target_id)
    """)


def downgrade() -> None:
    op.drop_table("relationships")
