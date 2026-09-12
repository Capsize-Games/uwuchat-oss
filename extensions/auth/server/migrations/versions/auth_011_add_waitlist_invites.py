"""Add waitlist_entries table.

Revision ID: auth_011
Revises: auth_010
Create Date: 2026-07-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from extensions.auth.server.migration_utils import has_table

revision = "auth_011"
down_revision = "auth_010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not has_table("waitlist_entries"):
        op.create_table(
            "waitlist_entries",
            sa.Column("id", sa.Integer(), autoincrement=True,
                      nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("ip_address", sa.String(64), nullable=True),
            sa.Column("token_hash", sa.String(), nullable=True),
            sa.Column("token_expires_at", sa.DateTime(), nullable=True),
            sa.Column("invited_at", sa.DateTime(), nullable=True),
            sa.Column("converted_account_id", sa.Integer(),
                      nullable=True),
            sa.Column("converted_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index(
            op.f("ix_waitlist_entries_email"),
            "waitlist_entries",
            ["email"],
        )
        op.create_foreign_key(
            "fk_waitlist_entries_account",
            "waitlist_entries",
            "accounts",
            ["converted_account_id"],
            ["id"],
        )


def downgrade() -> None:
    if has_table("waitlist_entries"):
        op.drop_table("waitlist_entries")
