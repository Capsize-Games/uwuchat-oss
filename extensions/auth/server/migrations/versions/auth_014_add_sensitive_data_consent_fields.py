"""Add sensitive-data consent fields to the accounts table.

Records explicit consent for Japan (APPI), India (DPDP Act), and
Canada (PIPEDA) — consent-based privacy regimes that do not have
GDPR's default-prohibition posture.  Mirrors the tos_agreed*
naming shape.

Revision ID: auth_014
Revises: auth_013
Create Date: 2026-07-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from extensions.auth.server.migration_utils import has_column

revision = "auth_014"
down_revision = "auth_013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        if not has_column("accounts", "sensitive_data_consent_agreed"):
            batch_op.add_column(
                sa.Column(
                    "sensitive_data_consent_agreed",
                    sa.Boolean(),
                    nullable=False,
                    server_default="false",
                )
            )
        if not has_column("accounts", "sensitive_data_consent_at"):
            batch_op.add_column(
                sa.Column(
                    "sensitive_data_consent_at",
                    sa.DateTime(),
                    nullable=True,
                )
            )
        if not has_column("accounts", "sensitive_data_consent_ip"):
            batch_op.add_column(
                sa.Column(
                    "sensitive_data_consent_ip",
                    sa.String(64),
                    nullable=True,
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        for col in (
            "sensitive_data_consent_ip",
            "sensitive_data_consent_at",
            "sensitive_data_consent_agreed",
        ):
            if has_column("accounts", col):
                batch_op.drop_column(col)
