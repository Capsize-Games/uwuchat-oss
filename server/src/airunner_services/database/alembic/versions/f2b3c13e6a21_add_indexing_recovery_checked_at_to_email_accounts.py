"""Add indexing_recovery_checked_at column to email_accounts.

Used as a debounce timestamp for the login-recovery hook —
``recover_pending_email_indexing`` checks this column before doing
any reconciliation or enqueue work, and skips if it was updated
within the cooldown window (currently 30 minutes).

Revision ID: f2b3c13e6a21
Revises: f2b3c13e6a20
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a21"
down_revision: Union[str, None] = "f2b3c13e6a20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Return True if *column* already exists on *table*."""
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def _table_exists(table: str) -> bool:
    """Return True if *table* exists in the current schema."""
    conn = op.get_bind()
    return sa.inspect(conn).has_table(table)


def upgrade() -> None:
    if _table_exists("email_accounts"):
        if not _column_exists("email_accounts", "indexing_recovery_checked_at"):
            op.add_column(
                "email_accounts",
                sa.Column(
                    "indexing_recovery_checked_at",
                    sa.DateTime(),
                    nullable=True,
                ),
            )


def downgrade() -> None:
    if _table_exists("email_accounts"):
        if _column_exists("email_accounts", "indexing_recovery_checked_at"):
            op.drop_column("email_accounts", "indexing_recovery_checked_at")
