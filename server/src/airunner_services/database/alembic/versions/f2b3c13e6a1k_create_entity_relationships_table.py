"""Create entity_relationships table.

Revision ID: f2b3c13e6a1k
Revises: f2b3c13e6a1j
Create Date: 2026-07-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1k"
down_revision: Union[str, None] = "f2b3c13e6a1j"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    """Return True if *table* already exists in the current schema."""
    conn = op.get_bind()
    return table in sa.inspect(conn).get_table_names()


def upgrade() -> None:
    if not _table_exists("entity_relationships"):
        op.create_table(
            "entity_relationships",
            sa.Column("id", sa.Integer, primary_key=True,
                      autoincrement=True),
            sa.Column("entity_a_id", sa.Integer, nullable=False,
                      index=True),
            sa.Column("entity_b_id", sa.Integer, nullable=False,
                      index=True),
            sa.Column("relationship_type", sa.String(32),
                      nullable=True),
            sa.Column("evidence_count", sa.Integer, nullable=False,
                      server_default="0"),
            sa.Column("strength", sa.Float, nullable=False,
                      server_default="0.0"),
            sa.Column("source", sa.String(32), nullable=False,
                      server_default="email_co_occurrence"),
            sa.Column("first_observed_at", sa.DateTime,
                      nullable=True),
            sa.Column("last_observed_at", sa.DateTime,
                      nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime, nullable=False,
                      server_default=sa.func.now()),
            sa.Column("deleted", sa.Boolean, nullable=False,
                      server_default=sa.text("false")),
            sa.UniqueConstraint(
                "entity_a_id", "entity_b_id", "source",
                name="uq_entity_relationship_edge",
            ),
        )


def downgrade() -> None:
    if _table_exists("entity_relationships"):
        op.drop_table("entity_relationships")
