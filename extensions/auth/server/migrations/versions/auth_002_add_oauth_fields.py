"""Add OAuth fields (google_id, auth_provider) to the accounts table.

Also makes ``password_hash`` nullable to support OAuth-only accounts that
have no password.

Revision ID: auth_002
Revises: auth_001
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from extensions.auth.server.migration_utils import has_column
from airunner_services.contract_enums import ModelService

revision = "auth_002"
down_revision = "auth_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: the auth chain can be re-applied during multi-tenant
    # provisioning (see migration_utils). Skip if columns already exist.
    if has_column("accounts", "google_id"):
        return
    # Use batch mode so SQLite (which cannot ALTER COLUMN in place) is
    # supported; on other backends batch emits plain ALTER statements.
    with op.batch_alter_table("accounts") as batch_op:
        # Allow NULL password_hash for OAuth-only accounts
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(),
            nullable=True,
        )
        batch_op.add_column(
            sa.Column("google_id", sa.String(), nullable=True),
        )
        batch_op.add_column(
            sa.Column(
                "auth_provider",
                sa.String(),
                nullable=False,
                server_default=ModelService.LOCAL.value,
            ),
        )
        batch_op.create_index(
            batch_op.f("ix_accounts_google_id"),
            ["google_id"],
            unique=True,
        )


def downgrade() -> None:
    if not has_column("accounts", "google_id"):
        return
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_index(batch_op.f("ix_accounts_google_id"))
        batch_op.drop_column("auth_provider")
        batch_op.drop_column("google_id")
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(),
            nullable=False,
        )
