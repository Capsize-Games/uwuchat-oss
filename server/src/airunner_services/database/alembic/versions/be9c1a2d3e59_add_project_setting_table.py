"""Add project_setting table for per-tenant key/value settings.

Revision ID: be9c1a2d3e59
Revises: be9c1a2d3e58
Create Date: 2026-06-16
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e59"
down_revision: Union[str, None] = "be9c1a2d3e58"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if not conn.execute(
        sa.text("SELECT to_regclass('project_setting')")
    ).scalar():
        op.create_table(
            "project_setting",
            sa.Column(
                "id", sa.Integer(), autoincrement=True, nullable=False
            ),
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("value", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.Column(
                "deleted",
                sa.Boolean(),
                nullable=True,
                server_default="false",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_project_setting_key",
            "project_setting",
            ["key"],
            unique=True,
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_project_setting_key"))
    conn.execute(sa.text("DROP TABLE IF EXISTS project_setting"))
