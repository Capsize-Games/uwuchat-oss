"""Add ``token_version`` to the accounts table for token revocation.

Incrementing an account's ``token_version`` invalidates all previously
issued refresh tokens (logout / "sign out everywhere"), since refresh
validates the token's ``ver`` claim against this column.

Revision ID: auth_003
Revises: auth_002
Create Date: 2026-06-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from extensions.auth.server.migration_utils import has_column

revision = "auth_003"
down_revision = "auth_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: see migration_utils — safe to re-apply during tenant
    # provisioning.
    if has_column("accounts", "token_version"):
        return
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "token_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    if not has_column("accounts", "token_version"):
        return
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_column("token_version")
