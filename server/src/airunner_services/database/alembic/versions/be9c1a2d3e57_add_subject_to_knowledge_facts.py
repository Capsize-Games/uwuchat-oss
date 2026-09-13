"""Add subject column to knowledge_facts.

Distinguishes facts the character knows about the user ('user', default)
from facts the character knows about itself ('self').  All existing rows
are backfilled to 'user' so behaviour is unchanged.

Revision ID: be9c1a2d3e57
Revises: be9c1a2d3e56
Create Date: 2026-06-15
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e57"
down_revision: Union[str, None] = "be9c1a2d3e56"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def _index_exists(index_name: str) -> bool:
    conn = op.get_bind()
    return any(
        idx["name"] == index_name
        for idx in sa.inspect(conn).get_indexes("knowledge_facts")
    )


def upgrade() -> None:
    if not _column_exists("knowledge_facts", "subject"):
        op.add_column(
            "knowledge_facts",
            sa.Column(
                "subject",
                sa.String(16),
                nullable=False,
                server_default="user",
            ),
        )
        op.get_bind().execute(
            sa.text(
                "UPDATE knowledge_facts SET subject = 'user'"
                " WHERE subject IS NULL OR subject = ''"
            )
        )
    if not _index_exists("ix_knowledge_facts_chatbot_subject"):
        op.create_index(
            "ix_knowledge_facts_chatbot_subject",
            "knowledge_facts",
            ["chatbot_id", "subject"],
        )


def downgrade() -> None:
    try:
        op.drop_index(
            "ix_knowledge_facts_chatbot_subject",
            table_name="knowledge_facts",
        )
    except Exception:
        pass
    if _column_exists("knowledge_facts", "subject"):
        op.drop_column("knowledge_facts", "subject")
