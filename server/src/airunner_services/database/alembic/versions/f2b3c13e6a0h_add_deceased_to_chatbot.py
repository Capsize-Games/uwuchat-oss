"""Add is_deceased, death_reason, deceased_at to chatbots.

Revision ID: f2b3c13e6a0h
Revises: f2b3c13e6a0g
Create Date: 2026-06-21 18:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from typing import Sequence, Union

revision: str = "f2b3c13e6a0h"
down_revision: Union[str, None] = "f2b3c13e6a0g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    """Add deceased fields to chatbots table."""
    if not _column_exists("chatbots", "is_deceased"):
        op.add_column(
            "chatbots",
            sa.Column(
                "is_deceased",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )
    if not _column_exists("chatbots", "death_reason"):
        op.add_column(
            "chatbots",
            sa.Column("death_reason", sa.Text(), nullable=True),
        )
    if not _column_exists("chatbots", "deceased_at"):
        op.add_column(
            "chatbots",
            sa.Column(
                "deceased_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )


def downgrade() -> None:
    """Remove deceased fields from chatbots table."""
    op.drop_column("chatbots", "deceased_at")
    op.drop_column("chatbots", "death_reason")
    op.drop_column("chatbots", "is_deceased")
