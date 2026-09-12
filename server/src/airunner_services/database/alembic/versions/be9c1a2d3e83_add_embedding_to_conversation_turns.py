"""Add embedding vector column to conversation_turns.

Enables pgvector similarity search in recall_conversation, replacing
SQL ILIKE.  Column is nullable so existing rows are preserved; embeddings
are computed lazily at first query time.

Revision ID: be9c1a2d3e83
Revises: be9c1a2d3e82
Create Date: 2026-06-20
"""

from alembic import op
import sqlalchemy as sa


revision = "be9c1a2d3e83"
down_revision = "be9c1a2d3e82"
branch_labels = None
depends_on = None

_EMBEDDING_DIM = 1024


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = [c["name"] for c in sa.inspect(conn).get_columns(table)]
    return column in cols


def upgrade():
    if not _column_exists("conversation_turns", "embedding"):
        op.add_column(
            "conversation_turns",
            sa.Column(
                "embedding",
                sa.Text(),
                nullable=True,
            ),
        )
        op.execute(
            f"ALTER TABLE conversation_turns "
            f"ALTER COLUMN embedding TYPE vector({_EMBEDDING_DIM}) "
            f"USING NULL"
        )
        op.create_index(
            "ix_conversation_turns_embedding_hnsw",
            "conversation_turns",
            ["embedding"],
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        )


def downgrade():
    op.drop_index("ix_conversation_turns_embedding_hnsw")
    op.drop_column("conversation_turns", "embedding")
