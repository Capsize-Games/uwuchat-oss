"""Add speech_patterns to chatbot.

Revision ID: f2b3c13e6a0i
Revises: f2b3c13e6a0h
Create Date: 2026-06-21
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "f2b3c13e6a0i"
down_revision: Union[str, None] = "f2b3c13e6a0h"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("chatbots", "speech_patterns"):
        op.add_column(
            "chatbots",
            sa.Column("speech_patterns", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("chatbots", "speech_patterns")
