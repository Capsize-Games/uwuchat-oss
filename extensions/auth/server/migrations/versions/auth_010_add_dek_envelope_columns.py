"""Add user-controlled-key envelope columns to accounts.

Revision ID: auth_010
Revises: auth_009
Create Date: 2026-07-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from extensions.auth.server.migration_utils import has_column

revision = "auth_010"
down_revision = "auth_009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # wrapped_dek — the Fernet-encrypted DEK (encrypted by the KEK)
    if not has_column("accounts", "wrapped_dek"):
        op.add_column(
            "accounts",
            sa.Column("wrapped_dek", sa.Text(), nullable=True),
        )

    # dek_kdf_salt — independent from Argon2 login-hash salt
    if not has_column("accounts", "dek_kdf_salt"):
        op.add_column(
            "accounts",
            sa.Column("dek_kdf_salt", sa.String(64), nullable=True),
        )

    # dek_kdf_params — stored per-account so KDF params can be upgraded
    if not has_column("accounts", "dek_kdf_params"):
        op.add_column(
            "accounts",
            sa.Column("dek_kdf_params", sa.JSON(), nullable=True),
        )

    # dek_version — bumped when DEK is rotated (e.g. after password change)
    if not has_column("accounts", "dek_version"):
        op.add_column(
            "accounts",
            sa.Column(
                "dek_version",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            ),
        )


def downgrade() -> None:
    if has_column("accounts", "dek_version"):
        op.drop_column("accounts", "dek_version")
    if has_column("accounts", "dek_kdf_params"):
        op.drop_column("accounts", "dek_kdf_params")
    if has_column("accounts", "dek_kdf_salt"):
        op.drop_column("accounts", "dek_kdf_salt")
    if has_column("accounts", "wrapped_dek"):
        op.drop_column("accounts", "wrapped_dek")
