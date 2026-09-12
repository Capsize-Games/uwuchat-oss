"""Add updated_at and deleted columns to conversation_events.

Revision ID: f2b3c13e6a0g
Revises: f2b3c13e6a0f
Create Date: 2026-06-21 15:32:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from typing import Sequence, Union

revision: str = "f2b3c13e6a0g"
down_revision: Union[str, None] = "f2b3c13e6a0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    """Add updated_at and deleted to conversation_events."""
    if not _column_exists("conversation_events", "updated_at"):
        op.add_column(
            "conversation_events",
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
    if not _column_exists("conversation_events", "deleted"):
        op.add_column(
            "conversation_events",
            sa.Column(
                "deleted",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )


def downgrade() -> None:
    """Remove updated_at and deleted from conversation_events."""
    if _column_exists("conversation_events", "deleted"):
        op.drop_column("conversation_events", "deleted")
    if _column_exists("conversation_events", "updated_at"):
        op.drop_column("conversation_events", "updated_at")
