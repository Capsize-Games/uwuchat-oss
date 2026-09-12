"""Widen prompt_preview/response_preview to Text columns.

Revision ID: f2b3c13e6a0u
Revises: f2b3c13e6a0t
Create Date: 2026-06-26
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a0u"
down_revision: Union[str, None] = "f2b3c13e6a0t"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "pipeline_token_usage",
        "prompt_preview",
        type_=sa.Text,
        existing_type=sa.String(200),
        existing_nullable=True,
    )
    op.alter_column(
        "pipeline_token_usage",
        "response_preview",
        type_=sa.Text,
        existing_type=sa.String(200),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "pipeline_token_usage",
        "prompt_preview",
        type_=sa.String(200),
        existing_type=sa.Text,
        existing_nullable=True,
    )
    op.alter_column(
        "pipeline_token_usage",
        "response_preview",
        type_=sa.String(200),
        existing_type=sa.Text,
        existing_nullable=True,
    )
