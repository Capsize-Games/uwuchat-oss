"""Add twitch_id column to accounts.

Revision ID: f2b3c13e6a0z
Revises: f2b3c13e6a0y
Create Date: 2026-06-30
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a0z"
down_revision: Union[str, None] = "f2b3c13e6a0y"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """Probe whether a column exists in the target schema."""
    inspector = sa.inspect(op.get_bind())
    return column in [
        c["name"] for c in inspector.get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("accounts", "twitch_id"):
        op.execute(
            sa.text(
                "ALTER TABLE accounts ADD COLUMN twitch_id "
                "VARCHAR UNIQUE"
            )
        )


def downgrade() -> None:
    if _column_exists("accounts", "twitch_id"):
        op.execute(
            sa.text(
                "ALTER TABLE accounts DROP COLUMN twitch_id"
            )
        )
