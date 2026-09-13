"""Replace ConversationTurn.embedding (plaintext pgvector) with
embedding_enc (CKKS-encrypted LargeBinary).

Drops the ``embedding`` column and its HNSW index
(``ix_conversation_turns_embedding_hnsw``), replacing it with
``embedding_enc`` (``LargeBinary``, nullable) to close the
embedding-inversion leak — the same class of fix already applied
to ``KnowledgeFact.embedding``.

Existing rows will have ``embedding_enc IS NULL`` after migration.
Since the session-close indexing job that populates this table has
never fired successfully in this codebase (0 rows, always), no
backfill is needed in practice.  When the indexing job is eventually
repaired, its write path now encrypts on write.

Revision ID: f2b3c13e6a1p
Revises: f2b3c13e6a1o
Create Date: 2026-07-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1p"
down_revision: Union[str, None] = "f2b3c13e6a1o"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    """Return True if *table* exists in the current schema."""
    conn = op.get_bind()
    return sa.inspect(conn).has_table(table)


def _column_exists(table: str, column: str) -> bool:
    """Return True if *column* already exists on *table*."""
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    # 1. Drop the HNSW index on conversation_turns.embedding.
    if _table_exists("conversation_turns"):
        op.execute(
            "DROP INDEX IF EXISTS ix_conversation_turns_embedding_hnsw"
        )

    # 2. Replace embedding column with embedding_enc.
    if _table_exists("conversation_turns"):
        if _column_exists("conversation_turns", "embedding"):
            op.drop_column("conversation_turns", "embedding")
        if not _column_exists("conversation_turns", "embedding_enc"):
            op.add_column(
                "conversation_turns",
                sa.Column(
                    "embedding_enc",
                    sa.LargeBinary,
                    nullable=True,
                ),
            )


def downgrade() -> None:
    # Reverse: drop embedding_enc, restore embedding column + index.
    if _table_exists("conversation_turns"):
        if _column_exists("conversation_turns", "embedding_enc"):
            op.drop_column("conversation_turns", "embedding_enc")
        if not _column_exists("conversation_turns", "embedding"):
            from pgvector.sqlalchemy import Vector

            embedding_dim = 1024
            op.add_column(
                "conversation_turns",
                sa.Column(
                    "embedding",
                    Vector(embedding_dim),
                    nullable=True,
                ),
            )
            op.create_index(
                "ix_conversation_turns_embedding_hnsw",
                "conversation_turns",
                ["embedding"],
                postgresql_using="hnsw",
                postgresql_ops={"embedding": "vector_cosine_ops"},
            )
