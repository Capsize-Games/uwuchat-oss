"""Widen OpenRouter price columns to prevent numeric overflow.

Revision ID: f2b3c13e6a0n
Revises: f2b3c13e6a0m
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from typing import Sequence, Union

revision: str = "f2b3c13e6a0n"
down_revision: Union[str, None] = "f2b3c13e6a0m"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in (
        "input_price_per_mtok",
        "output_price_per_mtok",
        "cache_read_per_mtok",
    ):
        op.alter_column(
            "openrouter_model",
            col,
            type_=sa.Numeric(20, 8),
            existing_type=sa.Numeric(14, 8),
            schema="public",
        )


def downgrade() -> None:
    pass
