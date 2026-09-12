"""Add items and cards tables for Phase 6 economy.

Revision ID: be9c1a2d3e70
Revises: be9c1a2d3e69
Create Date: 2026-06-16
"""

from typing import Union

from alembic import op

revision: str = "be9c1a2d3e70"
down_revision: Union[str, None] = "be9c1a2d3e69"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            item_type VARCHAR(32) NOT NULL DEFAULT 'misc',
            description TEXT,
            rarity VARCHAR(16) NOT NULL DEFAULT 'common',
            attributes JSONB,
            owned_by_chatbot_id INTEGER REFERENCES chatbots(id) ON DELETE SET NULL,
            location_found VARCHAR(128),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            transferred_at TIMESTAMP
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_items_owned_by_chatbot_id
        ON items (owned_by_chatbot_id)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS cards (
            id SERIAL PRIMARY KEY,
            chatbot_id INTEGER NOT NULL REFERENCES chatbots(id) ON DELETE CASCADE,
            ability_text TEXT,
            stats JSONB,
            art_url TEXT,
            owned_by_chatbot_id INTEGER REFERENCES chatbots(id) ON DELETE SET NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_cards_chatbot_id
        ON cards (chatbot_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_cards_owned_by_chatbot_id
        ON cards (owned_by_chatbot_id)
    """)


def downgrade() -> None:
    op.drop_table("cards")
    op.drop_table("items")
