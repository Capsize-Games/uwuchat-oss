"""Replace EmailBodyChunk.embedding (plaintext pgvector) with
embedding_enc (CKKS-encrypted LargeBinary).

Drops the ``embedding`` column and its HNSW index
(``ix_ebc_embedding_hnsw``), replacing it with ``embedding_enc``
(``LargeBinary``, nullable) to close the embedding-inversion leak.

Existing rows will have ``embedding_enc IS NULL`` after migration.
A bulk backfill is impossible — no DEK is available during offline
migration.  Rows with NULL embedding_enc are excluded from search
until the email sync pipeline re-indexes them (sync deletes-then-
reinserts each thread's chunks, so re-synced threads will get
encrypted embeddings naturally).

Revision ID: f2b3c13e6a1q
Revises: f2b3c13e6a1p
Create Date: 2026-07-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1q"
down_revision: Union[str, None] = "f2b3c13e6a1p"
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
    # 1. Drop the HNSW index on email_body_chunks.embedding.
    if _table_exists("email_body_chunks"):
        op.execute(
            "DROP INDEX IF EXISTS ix_ebc_embedding_hnsw"
        )

    # 2. Replace embedding column with embedding_enc.
    if _table_exists("email_body_chunks"):
        if _column_exists("email_body_chunks", "embedding"):
            op.drop_column("email_body_chunks", "embedding")
        if not _column_exists("email_body_chunks", "embedding_enc"):
            op.add_column(
                "email_body_chunks",
                sa.Column(
                    "embedding_enc",
                    sa.LargeBinary,
                    nullable=True,
                ),
            )


def downgrade() -> None:
    # Reverse: drop embedding_enc, restore embedding column + index.
    if _table_exists("email_body_chunks"):
        if _column_exists("email_body_chunks", "embedding_enc"):
            op.drop_column("email_body_chunks", "embedding_enc")
        if not _column_exists("email_body_chunks", "embedding"):
            from pgvector.sqlalchemy import Vector

            embedding_dim = 1024
            op.add_column(
                "email_body_chunks",
                sa.Column(
                    "embedding",
                    Vector(embedding_dim),
                    nullable=True,
                ),
            )
            op.execute(
                "CREATE INDEX IF NOT EXISTS ix_ebc_embedding_hnsw "
                "ON email_body_chunks "
                "USING hnsw (embedding vector_cosine_ops)"
            )
