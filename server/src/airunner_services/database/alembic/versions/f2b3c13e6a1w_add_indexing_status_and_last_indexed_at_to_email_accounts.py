"""Add indexing_status and last_indexed_at columns to email_accounts.

The DEK relay entry (Redis DB 2, TTL=600s) can expire before
_index_email_bodies_background runs, causing background indexing to
silently skip. This migration adds columns to track indexing state so
pending indexing can be retried when a live DEK is next available.

``indexing_status``: nullable String. Values:
  - ``"complete"`` — all threads have been indexed successfully
  - ``"pending"`` — background indexing was skipped due to missing DEK
  - ``None`` — account synced before this change (treated as unknown)

``last_indexed_at``: nullable DateTime. Set to ``utcnow()`` each time
background indexing completes successfully.

Revision ID: f2b3c13e6a1w
Revises: f2b3c13e6a1v
Create Date: 2026-07-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1w"
down_revision: Union[str, None] = "f2b3c13e6a1v"
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
        if not _column_exists("email_accounts", "indexing_status"):
            op.add_column(
                "email_accounts",
                sa.Column(
                    "indexing_status",
                    sa.String(16),
                    nullable=True,
                ),
            )
        if not _column_exists("email_accounts", "last_indexed_at"):
            op.add_column(
                "email_accounts",
                sa.Column(
                    "last_indexed_at",
                    sa.DateTime(),
                    nullable=True,
                ),
            )


def downgrade() -> None:
    if _table_exists("email_accounts"):
        if _column_exists("email_accounts", "indexing_status"):
            op.drop_column("email_accounts", "indexing_status")
        if _column_exists("email_accounts", "last_indexed_at"):
            op.drop_column("email_accounts", "last_indexed_at")
