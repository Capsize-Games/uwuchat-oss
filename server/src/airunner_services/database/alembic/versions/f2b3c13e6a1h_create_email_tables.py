"""Create email ingest tables (email_accounts, sync_checkpoints, etc.).

Revision ID: f2b3c13e6a1h
Revises: f2b3c13e6a1g
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "f2b3c13e6a1h"
down_revision: Union[str, None] = "f2b3c13e6a1g"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1024


def _table_exists(table: str) -> bool:
    """Return True if *table* already exists in the current schema."""
    conn = op.get_bind()
    return table in sa.inspect(conn).get_table_names()


def upgrade() -> None:
    # ── email_accounts ─────────────────────────────────────────────
    if not _table_exists("email_accounts"):
        op.create_table(
            "email_accounts",
            sa.Column("id", sa.Integer, primary_key=True,
                      autoincrement=True),
            sa.Column("user_id", sa.Integer, nullable=False,
                      index=True),
            sa.Column("provider", sa.String(32), nullable=False,
                      server_default="fastmail"),
            sa.Column("email_address", sa.String(255),
                      nullable=False),
            sa.Column("credential_ciphertext", sa.Text,
                      nullable=False),
            sa.Column("status", sa.String(16), nullable=False,
                      server_default="connected"),
            sa.Column("error_message", sa.String(512), nullable=True),
            sa.Column("sync_cursor", sa.String(255), nullable=True),
            sa.Column("backfill_completed_at", sa.DateTime,
                      nullable=True),
            sa.Column("last_synced_at", sa.DateTime, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("deleted", sa.Boolean, nullable=False,
                      server_default=sa.text("false")),
        )

    # ── email_sync_checkpoints ─────────────────────────────────────
    if not _table_exists("email_sync_checkpoints"):
        op.create_table(
            "email_sync_checkpoints",
            sa.Column("id", sa.Integer, primary_key=True,
                      autoincrement=True),
            sa.Column("email_account_id", sa.Integer, nullable=False,
                      index=True),
            sa.Column("mailbox_id", sa.String(255), nullable=False),
            sa.Column("mailbox_role", sa.String(32), nullable=False),
            sa.Column("last_position", sa.Integer, nullable=True),
            sa.Column("last_email_id", sa.String(255), nullable=True),
            sa.Column("emails_processed", sa.Integer, nullable=False,
                      server_default="0"),
            sa.Column("status", sa.String(16), nullable=False,
                      server_default="pending"),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("deleted", sa.Boolean, nullable=False,
                      server_default=sa.text("false")),
        )

    # ── email_messages ─────────────────────────────────────────────
    if not _table_exists("email_messages"):
        op.create_table(
            "email_messages",
            sa.Column("id", sa.Integer, primary_key=True,
                      autoincrement=True),
            sa.Column("email_account_id", sa.Integer, nullable=False,
                      index=True),
            sa.Column("provider_message_id", sa.String(255),
                      nullable=False, index=True),
            sa.Column("thread_id", sa.String(255), nullable=True,
                      index=True),
            sa.Column("mailbox_role", sa.String(32), nullable=False),
            sa.Column("from_address", sa.String(255), nullable=True),
            sa.Column("from_name", sa.String(255), nullable=True),
            sa.Column("to_addresses", sa.JSON, nullable=True),
            sa.Column("cc_addresses", sa.JSON, nullable=True),
            sa.Column("subject", sa.String(1024), nullable=True),
            sa.Column("sent_at", sa.DateTime, nullable=True,
                      index=True),
            sa.Column("has_attachments", sa.Boolean, nullable=False,
                      server_default=sa.text("false")),
            sa.Column("is_automated", sa.Boolean, nullable=False,
                      server_default=sa.text("false")),
            sa.Column("processed_at", sa.DateTime, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("deleted", sa.Boolean, nullable=False,
                      server_default=sa.text("false")),
        )

    # ── email_thread_summaries ─────────────────────────────────────
    if not _table_exists("email_thread_summaries"):
        op.create_table(
            "email_thread_summaries",
            sa.Column("id", sa.Integer, primary_key=True,
                      autoincrement=True),
            sa.Column("email_account_id", sa.Integer, nullable=False,
                      index=True),
            sa.Column("thread_id", sa.String(255), nullable=False,
                      index=True),
            sa.Column("summary_ciphertext", sa.Text, nullable=False),
            sa.Column("embedding", Vector(EMBEDDING_DIM),
                      nullable=True),
            sa.Column("participant_count", sa.Integer,
                      nullable=False, server_default="0"),
            sa.Column("message_count", sa.Integer, nullable=False,
                      server_default="0"),
            sa.Column("date_range_start", sa.DateTime, nullable=True),
            sa.Column("date_range_end", sa.DateTime, nullable=True),
            sa.Column("generated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("deleted", sa.Boolean, nullable=False,
                      server_default=sa.text("false")),
        )

    # ── email_contacts ─────────────────────────────────────────────
    if not _table_exists("email_contacts"):
        op.create_table(
            "email_contacts",
            sa.Column("id", sa.Integer, primary_key=True,
                      autoincrement=True),
            sa.Column("user_id", sa.Integer, nullable=False,
                      index=True),
            sa.Column("email_address", sa.String(255), nullable=False,
                      index=True),
            sa.Column("display_name", sa.String(255), nullable=True),
            sa.Column("first_seen_at", sa.DateTime, nullable=True),
            sa.Column("last_seen_at", sa.DateTime, nullable=True),
            sa.Column("message_count_from", sa.Integer,
                      nullable=False, server_default="0"),
            sa.Column("message_count_to", sa.Integer, nullable=False,
                      server_default="0"),
            sa.Column("avg_response_time_seconds", sa.Integer,
                      nullable=True),
            sa.Column("relationship_note_ciphertext", sa.Text,
                      nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("deleted", sa.Boolean, nullable=False,
                      server_default=sa.text("false")),
            sa.UniqueConstraint(
                "user_id", "email_address",
                name="uq_email_contacts_user_email",
            ),
        )

    # ── email_stats ────────────────────────────────────────────────
    if not _table_exists("email_stats"):
        op.create_table(
            "email_stats",
            sa.Column("id", sa.Integer, primary_key=True,
                      autoincrement=True),
            sa.Column("email_account_id", sa.Integer, nullable=False,
                      index=True),
            sa.Column("period", sa.String(16), nullable=False,
                      server_default="all_time"),
            sa.Column("total_messages", sa.Integer, nullable=False,
                      server_default="0"),
            sa.Column("sent_count", sa.Integer, nullable=False,
                      server_default="0"),
            sa.Column("received_count", sa.Integer, nullable=False,
                      server_default="0"),
            sa.Column("top_contacts", sa.JSON, nullable=True),
            sa.Column("computed_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("deleted", sa.Boolean, nullable=False,
                      server_default=sa.text("false")),
        )


def downgrade() -> None:
    for table in (
        "email_stats",
        "email_contacts",
        "email_thread_summaries",
        "email_messages",
        "email_sync_checkpoints",
        "email_accounts",
    ):
        if _table_exists(table):
            op.drop_table(table)
