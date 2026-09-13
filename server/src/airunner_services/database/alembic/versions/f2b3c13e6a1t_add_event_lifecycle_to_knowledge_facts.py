"""Add temporal event lifecycle columns to knowledge_facts.

Adds event_date, event_end_date, event_time, recurring, and
temporal_status columns to support structured tracking of
time-bound facts (deadlines, appointments, recurring events).

Existing rows default to temporal_status='durable' (no specific
date); all date/time columns are nullable.

Revision ID: f2b3c13e6a1t
Revises: f2b3c13e6a1s
Create Date: 2026-07-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1t"
down_revision: Union[str, None] = "f2b3c13e6a1s"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    """Return True if *table* exists in the current schema."""
    conn = op.get_bind()
    return sa.inspect(conn).has_table(table)


def _column_exists(table: str, column: str) -> bool:
    """Return True if *column* already exists on *table*."""
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _table_exists("knowledge_facts"):
        return

    if not _column_exists("knowledge_facts", "event_date"):
        op.add_column(
            "knowledge_facts",
            sa.Column("event_date", sa.Date, nullable=True),
        )

    if not _column_exists("knowledge_facts", "event_end_date"):
        op.add_column(
            "knowledge_facts",
            sa.Column("event_end_date", sa.Date, nullable=True),
        )

    if not _column_exists("knowledge_facts", "event_time"):
        op.add_column(
            "knowledge_facts",
            sa.Column("event_time", sa.Time, nullable=True),
        )

    if not _column_exists("knowledge_facts", "recurring"):
        op.add_column(
            "knowledge_facts",
            sa.Column(
                "recurring",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    if not _column_exists("knowledge_facts", "temporal_status"):
        op.add_column(
            "knowledge_facts",
            sa.Column(
                "temporal_status",
                sa.String(16),
                nullable=False,
                server_default="durable",
            ),
        )


def downgrade() -> None:
    if not _table_exists("knowledge_facts"):
        return

    for col in (
        "temporal_status",
        "recurring",
        "event_time",
        "event_end_date",
        "event_date",
    ):
        if _column_exists("knowledge_facts", col):
            op.drop_column("knowledge_facts", col)
