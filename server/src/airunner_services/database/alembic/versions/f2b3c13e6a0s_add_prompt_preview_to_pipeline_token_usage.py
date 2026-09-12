"""Add prompt_preview column to pipeline_token_usage.

Revision ID: f2b3c13e6a0s
Revises: f2b3c13e6a0r
Create Date: 2026-06-26
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a0s"
down_revision: Union[str, None] = "f2b3c13e6a0r"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if not _column_exists(
        "pipeline_token_usage", "prompt_preview"
    ):
        op.add_column(
            "pipeline_token_usage",
            sa.Column(
                "prompt_preview",
                sa.String(200),
                nullable=True,
            ),
        )
    if not _column_exists(
        "pipeline_token_usage", "response_preview"
    ):
        op.add_column(
            "pipeline_token_usage",
            sa.Column(
                "response_preview",
                sa.String(200),
                nullable=True,
            ),
        )


def downgrade() -> None:
    op.drop_column("pipeline_token_usage", "response_preview")
    op.drop_column("pipeline_token_usage", "prompt_preview")
