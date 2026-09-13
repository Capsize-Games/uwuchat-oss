"""Add allow_narrative_text column to chatbots.

Revision ID: f2b3c13e6a18
Revises: f2b3c13e6a17
Create Date: 2026-07-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a18"
down_revision: Union[str, None] = "f2b3c13e6a17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    """Add allow_narrative_text with default False."""
    if not _column_exists("chatbots", "allow_narrative_text"):
        op.add_column(
            "chatbots",
            sa.Column(
                "allow_narrative_text",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    """Remove allow_narrative_text column."""
    op.drop_column("chatbots", "allow_narrative_text")
