"""Add call_chain_id and chatbot_id for pipeline cost observability.

- public.pipeline_token_usage: add call_chain_id, chatbot_id
- tenant.conversation_turn: add call_chain_id

Revision ID: f2b3c13e6a0m
Revises: f2b3c13e6a0l
Create Date: 2026-06-22 14:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from typing import Sequence, Union

revision: str = "f2b3c13e6a0m"
down_revision: Union[str, None] = "f2b3c13e6a0l"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(table: str, column: str, schema: str = None) -> bool:
    conn = op.get_bind()
    cols = sa.inspect(conn).get_columns(table, schema=schema)
    return column in [c["name"] for c in cols]


def _table_exists(table: str, schema: str = "public") -> bool:
    conn = op.get_bind()
    return table in sa.inspect(conn).get_table_names(schema=schema)


def upgrade() -> None:
    """Add call-chain tracking columns."""
    if _table_exists("pipeline_token_usage", schema="public"):
        if not _col_exists(
            "pipeline_token_usage", "call_chain_id", schema="public"
        ):
            op.add_column(
                "pipeline_token_usage",
                sa.Column(
                    "call_chain_id", sa.String(36), nullable=True
                ),
                schema="public",
            )
            op.create_index(
                "ix_ptu_call_chain_id",
                "pipeline_token_usage",
                ["call_chain_id"],
                schema="public",
            )
        if not _col_exists(
            "pipeline_token_usage", "chatbot_id", schema="public"
        ):
            op.add_column(
                "pipeline_token_usage",
                sa.Column(
                    "chatbot_id", sa.Integer(), nullable=True
                ),
                schema="public",
            )
            op.create_index(
                "ix_ptu_chatbot_id",
                "pipeline_token_usage",
                ["chatbot_id"],
                schema="public",
            )

    if _table_exists("conversation_turn", schema=None):
        if not _col_exists("conversation_turn", "call_chain_id"):
            op.add_column(
                "conversation_turn",
                sa.Column(
                    "call_chain_id", sa.String(36), nullable=True
                ),
            )
            op.create_index(
                "ix_ct_call_chain_id",
                "conversation_turn",
                ["call_chain_id"],
            )


def downgrade() -> None:
    """Remove call-chain tracking columns."""
    if _table_exists("conversation_turn"):
        try:
            op.drop_index(
                "ix_ct_call_chain_id", table_name="conversation_turn"
            )
        except Exception:
            pass
        op.drop_column("conversation_turn", "call_chain_id")

    if _table_exists("pipeline_token_usage", schema="public"):
        try:
            op.drop_index(
                "ix_ptu_chatbot_id",
                table_name="pipeline_token_usage",
                schema="public",
            )
        except Exception:
            pass
        try:
            op.drop_index(
                "ix_ptu_call_chain_id",
                table_name="pipeline_token_usage",
                schema="public",
            )
        except Exception:
            pass
        op.drop_column(
            "pipeline_token_usage", "chatbot_id", schema="public"
        )
        op.drop_column(
            "pipeline_token_usage", "call_chain_id", schema="public"
        )
