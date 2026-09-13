"""Add co_occurrence_processed_at column to email_messages.

Revision ID: f2b3c13e6a1l
Revises: f2b3c13e6a1k
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1l"
down_revision: Union[str, None] = "f2b3c13e6a1k"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("email_messages", "co_occurrence_processed_at"):
        op.add_column(
            "email_messages",
            sa.Column("co_occurrence_processed_at", sa.DateTime,
                      nullable=True),
        )


def downgrade() -> None:
    if _column_exists("email_messages", "co_occurrence_processed_at"):
        op.drop_column("email_messages", "co_occurrence_processed_at")
