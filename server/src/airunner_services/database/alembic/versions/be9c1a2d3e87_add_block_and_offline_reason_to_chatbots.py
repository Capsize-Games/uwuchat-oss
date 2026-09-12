"""Add block_reason and offline_reason columns to chatbots.

Revision ID: be9c1a2d3e87
Revises: be9c1a2d3e86
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "be9c1a2d3e87"
down_revision = "be9c1a2d3e86"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("chatbots", "block_reason"):
        op.add_column(
            "chatbots",
            sa.Column("block_reason", sa.Text(), nullable=True),
        )
    if not _column_exists("chatbots", "offline_reason"):
        op.add_column(
            "chatbots",
            sa.Column("offline_reason", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("chatbots", "offline_reason"):
        op.drop_column("chatbots", "offline_reason")
    if _column_exists("chatbots", "block_reason"):
        op.drop_column("chatbots", "block_reason")
