"""Add pipeline_config, openrouter_model, pipeline_token_usage tables.

All live in the ``public`` schema (not per-tenant).

Revision ID: f2b3c13e6a0l
Revises: f2b3c13e6a0k
Create Date: 2026-06-22 12:00:00
"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from alembic import op
from typing import Sequence, Union

revision: str = "f2b3c13e6a0l"
down_revision: Union[str, None] = "f2b3c13e6a0k"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str, schema: str = "public") -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names(schema=schema)


def _base_columns():
    """Return the standard BaseModel columns applied to every table."""
    return [
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
            default=datetime.datetime.utcnow,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            default=datetime.datetime.utcnow,
            onupdate=datetime.datetime.utcnow,
        ),
        sa.Column(
            "deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    ]


def upgrade() -> None:
    """Create pipeline config, OpenRouter catalog, and token usage tables."""

    if not _table_exists("pipeline_config"):
        op.create_table(
            "pipeline_config",
            sa.Column(
                "id",
                sa.Integer(),
                primary_key=True,
                autoincrement=True,
            ),
            sa.Column(
                "pipeline_key",
                sa.String(64),
                unique=True,
                nullable=False,
            ),
            sa.Column(
                "overrides",
                sa.dialects.postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "updated_at_config",
                sa.DateTime(),
                nullable=True,
                default=datetime.datetime.utcnow,
            ),
            sa.Column("updated_by", sa.String(128), nullable=True),
            *_base_columns(),
            schema="public",
        )

    if not _table_exists("openrouter_model"):
        op.create_table(
            "openrouter_model",
            sa.Column(
                "id",
                sa.Integer(),
                primary_key=True,
                autoincrement=True,
            ),
            sa.Column(
                "model_id",
                sa.String(256),
                unique=True,
                nullable=False,
            ),
            sa.Column(
                "display_name", sa.String(256), nullable=True
            ),
            sa.Column(
                "input_price_per_mtok",
                sa.Numeric(14, 8),
                nullable=True,
            ),
            sa.Column(
                "output_price_per_mtok",
                sa.Numeric(14, 8),
                nullable=True,
            ),
            sa.Column(
                "cache_read_per_mtok",
                sa.Numeric(14, 8),
                nullable=True,
            ),
            sa.Column(
                "context_length", sa.Integer(), nullable=True
            ),
            sa.Column(
                "latency_p50_ms", sa.Integer(), nullable=True
            ),
            sa.Column(
                "throughput_tps",
                sa.Numeric(10, 2),
                nullable=True,
            ),
            sa.Column(
                "providers_json",
                sa.dialects.postgresql.JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "fetched_at",
                sa.DateTime(),
                nullable=True,
                default=datetime.datetime.utcnow,
            ),
            *_base_columns(),
            schema="public",
        )

    if not _table_exists("pipeline_token_usage"):
        op.create_table(
            "pipeline_token_usage",
            sa.Column(
                "id",
                sa.Integer(),
                primary_key=True,
                autoincrement=True,
            ),
            sa.Column(
                "pipeline_key",
                sa.String(64),
                nullable=False,
            ),
            sa.Column(
                "model_id", sa.String(256), nullable=False
            ),
            sa.Column(
                "input_tokens",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "output_tokens",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "cache_read_tokens",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
            sa.Column(
                "tenant_key",
                sa.String(128),
                nullable=True,
            ),
            sa.Column(
                "recorded_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "skipped",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "complexity_score",
                sa.Numeric(5, 4),
                nullable=True,
            ),
            sa.Column(
                "tier_name", sa.String(64), nullable=True
            ),
            sa.Column(
                "risk_score",
                sa.Numeric(5, 4),
                nullable=True,
            ),
            sa.Column(
                "risk_tier", sa.String(16), nullable=True
            ),
            sa.Column(
                "prompt_tokens_saved",
                sa.Integer(),
                nullable=True,
            ),
            *_base_columns(),
            schema="public",
        )

        op.create_index(
            "ix_ptu_key_recorded",
            "pipeline_token_usage",
            ["pipeline_key", "recorded_at"],
            schema="public",
        )
        op.create_index(
            "ix_pipeline_token_usage_tenant_key",
            "pipeline_token_usage",
            ["tenant_key"],
            schema="public",
        )


def downgrade() -> None:
    """Drop the three pipeline management tables."""
    op.drop_table("pipeline_token_usage", schema="public")
    op.drop_table("openrouter_model", schema="public")
    op.drop_table("pipeline_config", schema="public")
