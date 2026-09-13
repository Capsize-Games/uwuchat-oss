"""Drop unused Entity.embedding column.

Revision ID: f2b3c13e6a23
Revises: f2b3c13e6a22
Create Date: 2026-07-30

Entity.embedding was a dead plaintext-pgvector column — nothing ever
read or wrote it (see entity_resolver.py docstring).  Dropping it
removes unnecessary attack surface and schema clutter.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2b3c13e6a23"
down_revision = "f2b3c13e6a22"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return False
    return column in [c["name"] for c in inspector.get_columns(table)]


def upgrade() -> None:
    if _column_exists("entities", "embedding"):
        op.drop_column("entities", "embedding")


def downgrade() -> None:
    if not _column_exists("entities", "embedding"):
        op.add_column(
            "entities",
            sa.Column(
                "embedding",
                sa.NullType(),
                nullable=True,
            ),
        )
