"""Add omnipotent_knowledge column to chatbots.

Revision ID: f2b3c13e6a0r
Revises: f2b3c13e6a0q
Create Date: 2026-06-23
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a0r"
down_revision: Union[str, None] = "f2b3c13e6a0q"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("chatbots", "omnipotent_knowledge"):
        op.add_column(
            "chatbots",
            sa.Column(
                "omnipotent_knowledge",
                sa.Boolean,
                server_default=sa.false(),
                nullable=False,
            ),
        )


def downgrade() -> None:
    op.drop_column("chatbots", "omnipotent_knowledge")
