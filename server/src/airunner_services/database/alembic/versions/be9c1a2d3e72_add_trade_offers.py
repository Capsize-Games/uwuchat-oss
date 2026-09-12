"""Add trade_offers table for DM-based item/card trading.

Revision ID: be9c1a2d3e72
Revises: be9c1a2d3e71
Create Date: 2026-06-17
"""

from typing import Union

from alembic import op

revision: str = "be9c1a2d3e72"
down_revision: Union[str, None] = "be9c1a2d3e71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS trade_offers (
            id SERIAL PRIMARY KEY,
            offeror_chatbot_id INTEGER NOT NULL REFERENCES chatbots(id),
            offeree_chatbot_id INTEGER NOT NULL REFERENCES chatbots(id),
            offered_item_ids JSONB,
            offered_card_ids JSONB,
            requested_item_ids JSONB,
            requested_card_ids JSONB,
            message TEXT,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMP
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_trade_offers_offeror
        ON trade_offers (offeror_chatbot_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_trade_offers_offeree
        ON trade_offers (offeree_chatbot_id)
    """)


def downgrade() -> None:
    op.drop_table("trade_offers")
