"""Add composite quota index and HNSW vector indexes.

Composite (tenant_key, recorded_at) on pipeline_token_usage speeds up
the per-user quota query which filters on both columns.

HNSW indexes on knowledge_facts.embedding and document_chunks.embedding
replace sequential scans for cosine similarity search. Without them every
recall query is O(n) over all rows in the tenant schema.

Revision ID: f2b3c13e6a0w
Revises: f2b3c13e6a0v
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2b3c13e6a0w"
down_revision = "f2b3c13e6a0v"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    return sa.inspect(conn).has_table(table)


def _column_exists(table: str, column: str) -> bool:
    """Return True if *column* already exists on *table*."""
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    # Composite index for the quota endpoint (public schema, always present).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ptu_tenant_recorded "
        "ON public.pipeline_token_usage (tenant_key, recorded_at)"
    )

    # HNSW indexes for cosine-distance recall (tenant schemas only).
    # Check column existence as well as table — the embedding column may
    # have been removed by a later migration (f2b3c13e6a1o) when this
    # runs against a fresh schema via create_all (which reflects the
    # current model state).
    if _table_exists("knowledge_facts") and _column_exists(
        "knowledge_facts", "embedding",
    ):
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_kf_embedding_hnsw "
            "ON knowledge_facts "
            "USING hnsw (embedding vector_cosine_ops)"
        )
    if _table_exists("document_chunks"):
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_dc_embedding_hnsw "
            "ON document_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS public.ix_ptu_tenant_recorded"
    )
    op.execute("DROP INDEX IF EXISTS ix_kf_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_dc_embedding_hnsw")
