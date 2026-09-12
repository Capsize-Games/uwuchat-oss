"""Add call_chain_id column to conversation_turns (recovery migration).

The original migration f2b3c13e6a0m had a bug: _table_exists defaulted
to schema="public", so the column was never added to tenant schemas.
That migration already ran (as a no-op) and won't re-execute.  This
recovery migration applies the column unconditionally with an idempotent
existence check.

Revision ID: f2b3c13e6a0q
Revises: f2b3c13e6a0p
Create Date: 2026-06-23
"""

from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "f2b3c13e6a0q"
down_revision: Union[str, None] = "f2b3c13e6a0p"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists("conversation_turns", "call_chain_id"):
        op.add_column(
            "conversation_turns",
            sa.Column("call_chain_id", sa.String(36), nullable=True),
        )
        op.create_index(
            "ix_ct_call_chain_id",
            "conversation_turns",
            ["call_chain_id"],
        )


def downgrade() -> None:
    try:
        op.drop_index(
            "ix_ct_call_chain_id", table_name="conversation_turns"
        )
    except Exception:
        pass
    op.drop_column("conversation_turns", "call_chain_id")
