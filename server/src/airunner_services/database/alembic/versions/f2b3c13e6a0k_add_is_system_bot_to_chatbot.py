"""Add is_system_bot column to chatbots.

Revision ID: f2b3c13e6a0k
Revises: f2b3c13e6a0j
Create Date: 2026-06-21 20:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from typing import Sequence, Union

revision: str = "f2b3c13e6a0k"
down_revision: Union[str, None] = "f2b3c13e6a0j"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    """Add is_system_bot to chatbots."""
    if not _column_exists("chatbots", "is_system_bot"):
        op.add_column(
            "chatbots",
            sa.Column(
                "is_system_bot",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )


def downgrade() -> None:
    """Remove is_system_bot from chatbots."""
    op.drop_column("chatbots", "is_system_bot")
