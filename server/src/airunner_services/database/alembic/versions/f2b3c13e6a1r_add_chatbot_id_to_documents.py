"""Add chatbot_id to documents for per-chatbot scoping.

Revision ID: f2b3c13e6a1r
Revises: f2b3c13e6a1q
Create Date: 2026-07-21
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1r"
down_revision: Union[str, None] = "f2b3c13e6a1q"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    """Add nullable chatbot_id to documents with an index."""
    conn = op.get_bind()

    conn.execute(
        sa.text(
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS "
            "chatbot_id INTEGER"
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_documents_chatbot_id"
            " ON documents (chatbot_id)"
        )
    )


def downgrade() -> None:
    """Remove chatbot_id column and index from documents."""
    conn = op.get_bind()
    conn.execute(
        sa.text("DROP INDEX IF EXISTS ix_documents_chatbot_id")
    )
    conn.execute(
        sa.text(
            "ALTER TABLE documents DROP COLUMN IF EXISTS chatbot_id"
        )
    )
