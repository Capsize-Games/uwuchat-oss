"""Add cost tracking columns to pipeline_token_usage.

Revision ID: f2b3c13e6a1b
Revises: f2b3c13e6a19
Create Date: 2026-07-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1b"
down_revision: Union[str, None] = "f2b3c13e6a19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return column in [c["name"] for c in inspector.get_columns(table)]


def _index_exists(table: str, index: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return index in [i["name"] for i in inspector.get_indexes(table)]


def upgrade() -> None:
    if not _column_exists("pipeline_token_usage", "account_id"):
        op.add_column(
            "pipeline_token_usage",
            sa.Column("account_id", sa.Integer(), nullable=True),
        )
        op.create_index(
            op.f("ix_pipeline_token_usage_account_id"),
            "pipeline_token_usage",
            ["account_id"],
        )
    if not _column_exists(
        "pipeline_token_usage", "input_price_per_mtok"
    ):
        op.add_column(
            "pipeline_token_usage",
            sa.Column(
                "input_price_per_mtok",
                sa.Numeric(20, 8),
                nullable=True,
            ),
        )
    if not _column_exists(
        "pipeline_token_usage", "output_price_per_mtok"
    ):
        op.add_column(
            "pipeline_token_usage",
            sa.Column(
                "output_price_per_mtok",
                sa.Numeric(20, 8),
                nullable=True,
            ),
        )
    if not _column_exists(
        "pipeline_token_usage", "cache_price_per_mtok"
    ):
        op.add_column(
            "pipeline_token_usage",
            sa.Column(
                "cache_price_per_mtok",
                sa.Numeric(20, 8),
                nullable=True,
            ),
        )
    if not _column_exists("pipeline_token_usage", "cost_usd"):
        op.add_column(
            "pipeline_token_usage",
            sa.Column(
                "cost_usd", sa.Numeric(20, 8), nullable=True
            ),
        )
        op.create_index(
            op.f("ix_pipeline_token_usage_cost_usd"),
            "pipeline_token_usage",
            ["cost_usd"],
        )
    if not _index_exists(
        "pipeline_token_usage", "ix_ptu_account_recorded"
    ):
        op.create_index(
            "ix_ptu_account_recorded",
            "pipeline_token_usage",
            ["account_id", "recorded_at"],
        )


def downgrade() -> None:
    op.drop_index(
        "ix_ptu_account_recorded",
        table_name="pipeline_token_usage",
    )
    op.drop_index(
        op.f("ix_pipeline_token_usage_cost_usd"),
        table_name="pipeline_token_usage",
    )
    op.drop_column("pipeline_token_usage", "cost_usd")
    op.drop_column("pipeline_token_usage", "cache_price_per_mtok")
    op.drop_column("pipeline_token_usage", "output_price_per_mtok")
    op.drop_column("pipeline_token_usage", "input_price_per_mtok")
    op.drop_index(
        op.f("ix_pipeline_token_usage_account_id"),
        table_name="pipeline_token_usage",
    )
    op.drop_column("pipeline_token_usage", "account_id")
