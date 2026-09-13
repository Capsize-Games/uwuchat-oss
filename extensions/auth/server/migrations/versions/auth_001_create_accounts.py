"""Create the ``accounts`` table in the public schema.

Revision ID: auth_001
Revises:
Create Date: 2026-06-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from extensions.auth.server.migration_utils import has_table

revision = "auth_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ``accounts`` is a shared public-schema table; multi-tenant provisioning
    # can re-enter this migration within one upgrade pass. Skip if it already
    # exists so the second pass is a no-op rather than a DuplicateTable error.
    if has_table("accounts"):
        return
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=True, default=True),
        sa.Column(
            "is_verified", sa.Boolean(), nullable=True, default=False
        ),
        sa.Column(
            "is_superuser", sa.Boolean(), nullable=True, default=False
        ),
        sa.Column(
            "tenant_schema", sa.String(), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.Column(
            "last_login",
            sa.DateTime(),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
        ),
        sa.Column(
            "deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("tenant_schema"),
    )
    op.create_index(op.f("ix_accounts_email"), "accounts", ["email"])
    op.create_index(
        op.f("ix_accounts_username"), "accounts", ["username"]
    )


def downgrade() -> None:
    if not has_table("accounts"):
        return
    op.drop_index(op.f("ix_accounts_username"), table_name="accounts")
    op.drop_index(op.f("ix_accounts_email"), table_name="accounts")
    op.drop_table("accounts")
