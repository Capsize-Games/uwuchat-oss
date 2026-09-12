"""add knowledge_mode to chatbot

Revision ID: be9c1a2d3e80
Revises: be9c1a2d3e79
Create Date: 2026-06-19
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e80"
down_revision: Union[str, None] = "be9c1a2d3e79"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("chatbots", "knowledge_mode"):
        op.add_column(
            "chatbots",
            sa.Column(
                "knowledge_mode",
                sa.String,
                server_default="omniscient",
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_column("chatbots", "knowledge_mode")
