"""Replace email_thread_summaries with chunked email_body_chunks.

Drops the lossy one-summary-per-thread table in favor of persisted,
chunked, per-user-encrypted email body content (see
projects/uwuchat/server/email/email_body_indexer.py). Dev-only data —
there is no meaningful forward migration from a summary to real body
chunks, since raw bodies were never stored in the old design.

Revision ID: f2b3c13e6a1n
Revises: f2b3c13e6a1m
Create Date: 2026-07-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "f2b3c13e6a1n"
down_revision: Union[str, None] = "f2b3c13e6a1m"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1024


def _table_exists(table: str) -> bool:
    """Return True if *table* already exists in the current schema."""
    conn = op.get_bind()
    return table in sa.inspect(conn).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    """Return True if *column* already exists on *table*."""
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    if _table_exists("email_thread_summaries"):
        op.drop_table("email_thread_summaries")

    if not _table_exists("email_body_chunks"):
        op.create_table(
            "email_body_chunks",
            sa.Column("id", sa.Integer, primary_key=True,
                      autoincrement=True),
            sa.Column("email_account_id", sa.Integer, nullable=False,
                      index=True),
            sa.Column("thread_id", sa.String(255), nullable=False,
                      index=True),
            sa.Column("chunk_index", sa.Integer, nullable=False,
                      server_default="0"),
            sa.Column("content_ciphertext", sa.Text, nullable=False),
            sa.Column("embedding", Vector(EMBEDDING_DIM),
                      nullable=True),
            sa.Column("participant_count", sa.Integer,
                      nullable=False, server_default="0"),
            sa.Column("message_count", sa.Integer, nullable=False,
                      server_default="0"),
            sa.Column("date_range_start", sa.DateTime, nullable=True),
            sa.Column("date_range_end", sa.DateTime, nullable=True),
            sa.Column("generated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("deleted", sa.Boolean, nullable=False,
                      server_default=sa.text("false")),
            sa.UniqueConstraint(
                "email_account_id", "thread_id", "chunk_index",
                name="uq_email_body_chunks_thread_idx",
            ),
        )

    # A later migration (f2b3c13e6a1q) drops the "embedding" column
    # entirely once a schema has already moved past this point.  Only
    # (re)create the HNSW index when that column still exists --
    # otherwise this step has nothing to do (superseded), not an
    # error.
    if _table_exists("email_body_chunks") and _column_exists(
        "email_body_chunks", "embedding"
    ):
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_ebc_embedding_hnsw "
            "ON email_body_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ebc_embedding_hnsw")
    if _table_exists("email_body_chunks"):
        op.drop_table("email_body_chunks")
    # Old table is not recreated — data is gone either way.
