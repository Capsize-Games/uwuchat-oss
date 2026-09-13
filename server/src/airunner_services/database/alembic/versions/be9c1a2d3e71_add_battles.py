"""Add battles table for card battle system.

Revision ID: be9c1a2d3e71
Revises: be9c1a2d3e70
Create Date: 2026-06-16
"""

from typing import Union

from alembic import op

revision: str = "be9c1a2d3e71"
down_revision: Union[str, None] = "be9c1a2d3e70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS battles (
            id SERIAL PRIMARY KEY,
            challenger_id INTEGER NOT NULL REFERENCES chatbots(id),
            defender_id INTEGER NOT NULL REFERENCES chatbots(id),
            winner_id INTEGER REFERENCES chatbots(id),
            rounds JSONB,
            result_summary TEXT,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMP
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_battles_challenger_id
        ON battles (challenger_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_battles_defender_id
        ON battles (defender_id)
    """)


def downgrade() -> None:
    op.drop_table("battles")
