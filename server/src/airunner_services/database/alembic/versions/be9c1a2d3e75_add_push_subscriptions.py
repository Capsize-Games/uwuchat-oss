"""Add push_subscriptions table for Web Push.

Revision ID: be9c1a2d3e75
Revises: be9c1a2d3e74
Create Date: 2026-06-17
"""

from typing import Union

from alembic import op

revision: str = "be9c1a2d3e75"
down_revision: Union[str, None] = "be9c1a2d3e74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id SERIAL PRIMARY KEY,
            account_id INTEGER NOT NULL,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            deleted BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMP
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_push_subscriptions_account_id "
        "ON push_subscriptions (account_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS push_subscriptions")
