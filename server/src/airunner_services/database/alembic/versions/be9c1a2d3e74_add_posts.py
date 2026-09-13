"""Add posts table for UwU social posts (lazy content generation).

Revision ID: be9c1a2d3e74
Revises: be9c1a2d3e73
Create Date: 2026-06-17
"""

from typing import Union

from alembic import op

revision: str = "be9c1a2d3e74"
down_revision: Union[str, None] = "be9c1a2d3e73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id SERIAL PRIMARY KEY,
            chatbot_id INTEGER NOT NULL REFERENCES chatbots(id),
            content TEXT,
            context_snapshot JSONB,
            visibility VARCHAR(16) NOT NULL DEFAULT 'public',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            generated_at TIMESTAMP,
            deleted BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_posts_chatbot_id "
        "ON posts (chatbot_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_posts_created_at "
        "ON posts (created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS posts")
