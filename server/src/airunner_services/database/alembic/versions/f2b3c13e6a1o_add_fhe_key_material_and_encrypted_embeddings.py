"""Add fhe_key_material table and replace KnowledgeFact.embedding with
encrypted embedding column.

Creates the ``fhe_key_material`` table (one row per account) storing
the TenSEAL public context and DEK-wrapped secret key.

Drops the ``embedding`` pgvector column and its HNSW index from
``knowledge_facts``, replacing it with ``embedding_enc``
(``LargeBinary``, nullable) that stores CKKS-encrypted embedding
vectors.

Existing rows will have ``embedding_enc IS NULL`` after migration.
They will be lazily re-embedded on next write when a live DEK is
available (via the re-embed-on-miss path in knowledge_crud.py).
Facts that are never revisited simply have NULL embedding_enc and
are excluded from vector search — this is an explicit tradeoff:
a bulk backfill is impossible because no DEK is available during
offline migration.

Revision ID: f2b3c13e6a1o
Revises: f2b3c13e6a1n
Create Date: 2026-07-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1o"
down_revision: Union[str, None] = "f2b3c13e6a1n"
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
    # 1. Create fhe_key_material table (if not already present).
    if not _table_exists("fhe_key_material"):
        op.create_table(
            "fhe_key_material",
            sa.Column(
                "account_id",
                sa.Integer,
                primary_key=True,
                autoincrement=False,
            ),
            sa.Column(
                "public_context",
                sa.LargeBinary,
                nullable=False,
            ),
            sa.Column(
                "secret_key_wrapped",
                sa.LargeBinary,
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime,
                nullable=True,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime,
                nullable=True,
            ),
            sa.Column(
                "deleted",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    # 2. Drop the HNSW index on knowledge_facts.embedding.
    if _table_exists("knowledge_facts"):
        op.execute(
            "DROP INDEX IF EXISTS ix_kf_embedding_hnsw"
        )

    # 3. Replace embedding column with embedding_enc.
    if _table_exists("knowledge_facts"):
        if _column_exists("knowledge_facts", "embedding"):
            op.drop_column("knowledge_facts", "embedding")
        if not _column_exists("knowledge_facts", "embedding_enc"):
            op.add_column(
                "knowledge_facts",
                sa.Column(
                    "embedding_enc",
                    sa.LargeBinary,
                    nullable=True,
                ),
            )


def downgrade() -> None:
    # Reverse: drop embedding_enc, restore embedding column.
    if _table_exists("knowledge_facts"):
        if _column_exists("knowledge_facts", "embedding_enc"):
            op.drop_column("knowledge_facts", "embedding_enc")
        if not _column_exists("knowledge_facts", "embedding"):
            from pgvector.sqlalchemy import Vector

            embedding_dim = 1024
            op.add_column(
                "knowledge_facts",
                sa.Column(
                    "embedding",
                    Vector(embedding_dim),
                    nullable=True,
                ),
            )

    # Drop fhe_key_material.
    if _table_exists("fhe_key_material"):
        op.drop_table("fhe_key_material")
