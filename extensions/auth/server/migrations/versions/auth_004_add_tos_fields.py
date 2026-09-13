"""Add ToS agreement fields to the accounts table.

Stores the explicit agreement flags captured at registration (or via the
post-OAuth agree-tos endpoint) plus the timestamp and IP for audit purposes.

Revision ID: auth_004
Revises: auth_003
Create Date: 2026-06-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from extensions.auth.server.migration_utils import has_column

revision = "auth_004"
down_revision = "auth_003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        if not has_column("accounts", "tos_agreed"):
            batch_op.add_column(
                sa.Column(
                    "tos_agreed",
                    sa.Boolean(),
                    nullable=False,
                    server_default="false",
                )
            )
        if not has_column("accounts", "age_confirmed"):
            batch_op.add_column(
                sa.Column(
                    "age_confirmed",
                    sa.Boolean(),
                    nullable=False,
                    server_default="false",
                )
            )
        if not has_column("accounts", "entertainment_confirmed"):
            batch_op.add_column(
                sa.Column(
                    "entertainment_confirmed",
                    sa.Boolean(),
                    nullable=False,
                    server_default="false",
                )
            )
        if not has_column("accounts", "tos_agreed_at"):
            batch_op.add_column(
                sa.Column("tos_agreed_at", sa.DateTime(), nullable=True)
            )
        if not has_column("accounts", "tos_agreed_ip"):
            batch_op.add_column(
                sa.Column(
                    "tos_agreed_ip", sa.String(64), nullable=True
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        for col in (
            "tos_agreed_ip",
            "tos_agreed_at",
            "entertainment_confirmed",
            "age_confirmed",
            "tos_agreed",
        ):
            if has_column("accounts", col):
                batch_op.drop_column(col)
