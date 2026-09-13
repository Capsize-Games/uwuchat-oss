"""Add output_language and language_proficiency columns to chatbots.

Revision ID: f2b3c13e6a0x
Revises: f2b3c13e6a0w
Create Date: 2026-06-28
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a0x"
down_revision: Union[str, None] = "f2b3c13e6a0w"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """Probe whether a column exists in the target schema."""
    inspector = sa.inspect(op.get_bind())
    return column in [
        c["name"] for c in inspector.get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("chatbots", "output_language"):
        op.execute(
            sa.text(
                "ALTER TABLE chatbots ADD COLUMN output_language "
                "VARCHAR"
            )
        )
    if not _column_exists("chatbots", "language_proficiency"):
        op.execute(
            sa.text(
                "ALTER TABLE chatbots ADD COLUMN language_proficiency "
                "VARCHAR NOT NULL DEFAULT 'fluent'"
            )
        )


def downgrade() -> None:
    if _column_exists("chatbots", "output_language"):
        op.execute(
            sa.text(
                "ALTER TABLE chatbots DROP COLUMN output_language"
            )
        )
    if _column_exists("chatbots", "language_proficiency"):
        op.execute(
            sa.text(
                "ALTER TABLE chatbots DROP COLUMN language_proficiency"
            )
        )
