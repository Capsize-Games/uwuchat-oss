"""add curiosity_questions table

Revision ID: be9c1a2d3e82
Revises: be9c1a2d3e81
Create Date: 2026-06-20
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e82"
down_revision: Union[str, None] = "be9c1a2d3e81"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    return sa.inspect(conn).has_table(table)


def upgrade() -> None:
    if _table_exists("curiosity_questions"):
        return
    op.create_table(
        "curiosity_questions",
        sa.Column(
            "id", sa.Integer, primary_key=True, autoincrement=True
        ),
        sa.Column("chatbot_id", sa.Integer, nullable=False),
        sa.Column("entity", sa.Text, nullable=False),
        sa.Column("missing", sa.Text, nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime, nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime, nullable=True
        ),
        sa.Column(
            "deleted", sa.Boolean, nullable=False, server_default="false"
        ),
    )
    op.create_index(
        "ix_curiosity_questions_chatbot_id",
        "curiosity_questions",
        ["chatbot_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_curiosity_questions_chatbot_id",
        table_name="curiosity_questions",
    )
    op.drop_table("curiosity_questions")
