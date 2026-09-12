"""Create calendar_events table with new recurring-reminder columns.

Revision ID: f2b3c13e6a17
Revises: f2b3c13e6a16
Create Date: 2026-07-04
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a17"
down_revision: Union[str, None] = "f2b3c13e6a16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Check whether *column* exists in *table* in the current schema."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return column in [
        c["name"] for c in inspector.get_columns(table)
    ]


def upgrade() -> None:
    """Create calendar_events table or add missing columns idempotently."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "calendar_events" not in inspector.get_table_names():
        op.create_table(
            "calendar_events",
            sa.Column("id", sa.Integer(), autoincrement=True,
                      nullable=False),
            sa.Column(
                "user_id", sa.Integer(),
                sa.ForeignKey("users.id"), nullable=False,
            ),
            sa.Column(
                "chatbot_id", sa.Integer(),
                sa.ForeignKey("chatbots.id"), nullable=True,
            ),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "starts_at", sa.DateTime(timezone=True), nullable=False,
            ),
            sa.Column(
                "ends_at", sa.DateTime(timezone=True), nullable=True,
            ),
            sa.Column("all_day", sa.Boolean(), nullable=False,
                      server_default=sa.false()),
            sa.Column("recurrence_rule", sa.String(255), nullable=True),
            sa.Column("google_event_id", sa.String(255), nullable=True),
            sa.Column("reminder_minutes", sa.Integer(), nullable=True),
            sa.Column(
                "created_at", sa.DateTime(),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(),
                server_default=sa.func.now(), nullable=False,
            ),
            sa.Column("deleted", sa.Boolean(), server_default=sa.false(),
                      nullable=False),
            sa.Column("is_recurring_reminder", sa.Boolean(),
                      server_default=sa.false(), nullable=False),
            sa.Column("recurrence_days", sa.String(255), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.Index("ix_calendar_events_user_id", "user_id"),
        )
        return

    # Table already exists (e.g. from create_all).  Add new columns
    # idempotently, probing each before creation.
    if not _column_exists("calendar_events", "is_recurring_reminder"):
        op.add_column(
            "calendar_events",
            sa.Column("is_recurring_reminder", sa.Boolean(),
                      server_default=sa.false(), nullable=False),
        )

    if not _column_exists("calendar_events", "recurrence_days"):
        op.add_column(
            "calendar_events",
            sa.Column("recurrence_days", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    """Drop the new columns (does not drop the table)."""
    if _column_exists("calendar_events", "recurrence_days"):
        op.drop_column("calendar_events", "recurrence_days")
    if _column_exists("calendar_events", "is_recurring_reminder"):
        op.drop_column("calendar_events", "is_recurring_reminder")
