"""Add chatbot presence and block fields.

Revision ID: be9c1a2d3e86
Revises: be9c1a2d3e85
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "be9c1a2d3e86"
down_revision = "be9c1a2d3e85"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("chatbots", "is_online"):
        op.add_column(
            "chatbots",
            sa.Column(
                "is_online",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
        )
    if not _column_exists("chatbots", "offline_until"):
        op.add_column(
            "chatbots",
            sa.Column(
                "offline_until",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )
    if not _column_exists("chatbots", "has_blocked_user"):
        op.add_column(
            "chatbots",
            sa.Column(
                "has_blocked_user",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if not _column_exists("chatbots", "blocked_by_user"):
        op.add_column(
            "chatbots",
            sa.Column(
                "blocked_by_user",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    for col in (
        "blocked_by_user",
        "has_blocked_user",
        "offline_until",
        "is_online",
    ):
        if _column_exists("chatbots", col):
            op.drop_column("chatbots", col)
