"""Create entities table.

Revision ID: f2b3c13e6a1i
Revises: f2b3c13e6a1h
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "f2b3c13e6a1i"
down_revision: Union[str, None] = "f2b3c13e6a1h"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMBEDDING_DIM = 1024


def _table_exists(table: str) -> bool:
    """Return True if *table* already exists in the current schema."""
    conn = op.get_bind()
    return table in sa.inspect(conn).get_table_names()


def upgrade() -> None:
    if not _table_exists("entities"):
        op.create_table(
            "entities",
            sa.Column("id", sa.Integer, primary_key=True,
                      autoincrement=True),
            sa.Column("entity_type", sa.String(32), nullable=False,
                      server_default="person"),
            sa.Column("chatbot_id", sa.Integer, nullable=True,
                      index=True),
            sa.Column("display_name_ct", sa.Text, nullable=False),
            sa.Column("name_lookup_hash", sa.String(64),
                      nullable=False, index=True),
            sa.Column("aliases_ct", sa.Text, nullable=True),
            sa.Column("embedding", Vector(EMBEDDING_DIM),
                      nullable=True),
            sa.Column("source_type", sa.String(32), nullable=False,
                      server_default="inferred"),
            sa.Column("source_ref_table", sa.String(64),
                      nullable=True),
            sa.Column("source_ref_id", sa.Integer, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("deleted", sa.Boolean, nullable=False,
                      server_default=sa.text("false")),
        )


def downgrade() -> None:
    if _table_exists("entities"):
        op.drop_table("entities")
