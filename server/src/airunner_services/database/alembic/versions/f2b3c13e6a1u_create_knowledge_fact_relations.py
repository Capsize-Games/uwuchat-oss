"""Create knowledge_fact_relations join table with FK constraints.

Schemas are qualified explicitly because has_table() finds tables
in public when the search_path includes it.

Revision ID: f2b3c13e6a1u
Revises: f2b3c13e6a1t
Create Date: 2026-07-26
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1u"
down_revision: Union[str, None] = "f2b3c13e6a1t"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _current_schema() -> str | None:
    conn = op.get_bind()
    return conn.execute(sa.text("SELECT current_schema()")).scalar()


def _table_in_schema(schema: str, table: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names(schema=schema)


def upgrade() -> None:
    schema = _current_schema()
    if schema is None or schema == "public":
        return
    if _table_in_schema(schema, "knowledge_fact_relations"):
        return

    op.execute(
        sa.text(
            f"CREATE TABLE {schema}.knowledge_fact_relations ("
            "  id SERIAL PRIMARY KEY,"
            "  fact_id INTEGER NOT NULL,"
            "  related_fact_id INTEGER NOT NULL,"
            "  relation_type VARCHAR(16) NOT NULL,"
            "  created_at TIMESTAMP NOT NULL,"
            "  updated_at TIMESTAMP,"
            "  deleted BOOLEAN NOT NULL DEFAULT false,"
            f"  CONSTRAINT uq_knowledge_fact_relation"
            f"    UNIQUE (fact_id, related_fact_id, relation_type),"
            f"  CONSTRAINT kfr_fact_fkey"
            f"    FOREIGN KEY (fact_id)"
            f"    REFERENCES {schema}.knowledge_facts (id)"
            f"    ON DELETE CASCADE,"
            f"  CONSTRAINT kfr_rel_fkey"
            f"    FOREIGN KEY (related_fact_id)"
            f"    REFERENCES {schema}.knowledge_facts (id)"
            f"    ON DELETE CASCADE"
            ")"
        )
    )
    op.create_index(
        "ix_kfr_fact_id", "knowledge_fact_relations", ["fact_id"]
    )
    op.create_index(
        "ix_kfr_rel_fact_id", "knowledge_fact_relations",
        ["related_fact_id"],
    )


def downgrade() -> None:
    schema = _current_schema()
    if schema and schema != "public" and _table_in_schema(
        schema, "knowledge_fact_relations"
    ):
        op.drop_table("knowledge_fact_relations")
