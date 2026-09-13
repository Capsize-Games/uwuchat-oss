"""Replace prompt_preview/response_preview with char-count metadata.

Removes plaintext content-bearing columns from the public-schema
pipeline_token_usage table and replaces them with privacy-safe
character-count Integer columns per CLAUDE.md Security rules.

Revision ID: f2b3c13e6a1c
Revises: f2b3c13e6a1b
Create Date: 2026-07-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1c"
down_revision: Union[str, None] = "f2b3c13e6a1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "pipeline_token_usage"


def _column_exists(column: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return column in [c["name"] for c in inspector.get_columns(TABLE)]


def upgrade() -> None:
    # Remove old plaintext content columns.
    if _column_exists("prompt_preview"):
        op.drop_column(TABLE, "prompt_preview")
    if _column_exists("response_preview"):
        op.drop_column(TABLE, "response_preview")
    # Add privacy-safe character-count metadata.
    if not _column_exists("prompt_char_count"):
        op.add_column(
            TABLE,
            sa.Column("prompt_char_count", sa.Integer(), nullable=True),
        )
    if not _column_exists("response_char_count"):
        op.add_column(
            TABLE,
            sa.Column("response_char_count", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    # Reverse: drop char-count columns, re-add text columns.
    if _column_exists("prompt_char_count"):
        op.drop_column(TABLE, "prompt_char_count")
    if _column_exists("response_char_count"):
        op.drop_column(TABLE, "response_char_count")
    if not _column_exists("prompt_preview"):
        op.add_column(
            TABLE, sa.Column("prompt_preview", sa.Text(), nullable=True),
        )
    if not _column_exists("response_preview"):
        op.add_column(
            TABLE,
            sa.Column("response_preview", sa.Text(), nullable=True),
        )
