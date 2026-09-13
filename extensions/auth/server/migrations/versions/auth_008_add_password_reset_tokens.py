"""Add password_reset_tokens table.

Revision ID: auth_008
Revises: auth_007
Create Date: 2026-07-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from extensions.auth.server.migration_utils import has_table

revision = "auth_008"
down_revision = "auth_007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if has_table("password_reset_tokens"):
        return

    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "account_id",
            sa.Integer(),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "token_hash",
            sa.String(),
            nullable=False,
            unique=True,
            index=True,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(),
            nullable=False,
        ),
        sa.Column(
            "used",
            sa.Boolean(),
            nullable=False,
            default=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    if has_table("password_reset_tokens"):
        op.drop_table("password_reset_tokens")
