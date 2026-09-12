"""Add chatbot_id to knowledge_facts and knowledge_tags for agent scoping.

Revision ID: be9c1a2d3e53
Revises: be9c1a2d3e52
Create Date: 2026-06-14
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e53"
down_revision: Union[str, None] = "be9c1a2d3e52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── knowledge_facts ────────────────────────────────────────────────
    # Use IF NOT EXISTS so this is safe regardless of which schema the
    # table resolves to via search_path (avoids DuplicateColumn when the
    # column already exists in public and the tenant table isn't yet present).
    conn.execute(
        sa.text(
            "ALTER TABLE knowledge_facts ADD COLUMN IF NOT EXISTS chatbot_id INTEGER"
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_knowledge_facts_chatbot_id"
            " ON knowledge_facts (chatbot_id)"
        )
    )

    # ── knowledge_tags — drop old global unique constraint first ────────
    # Use IF EXISTS so no transaction is aborted when the constraint is
    # already absent (common on a fresh schema).
    conn.execute(
        sa.text(
            "ALTER TABLE knowledge_tags DROP CONSTRAINT IF EXISTS uq_knowledge_tag_name"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE knowledge_tags DROP CONSTRAINT IF EXISTS knowledge_tags_name_key"
        )
    )

    conn.execute(
        sa.text(
            "ALTER TABLE knowledge_tags ADD COLUMN IF NOT EXISTS chatbot_id INTEGER"
        )
    )
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_knowledge_tags_chatbot_id"
            " ON knowledge_tags (chatbot_id)"
        )
    )

    # Guard: only add the composite unique constraint if absent on the table
    # visible via search_path (to_regclass finds public.knowledge_tags when
    # running against a tenant URL; information_schema+current_schema() would
    # miss it and re-attempt the constraint, failing with DuplicateObject).
    has_new_constraint = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "WHERE c.conname = 'uq_knowledge_tag_name_chatbot' "
            "AND t.oid = to_regclass('knowledge_tags')"
        )
    ).scalar()
    if not has_new_constraint:
        op.create_unique_constraint(
            "uq_knowledge_tag_name_chatbot",
            "knowledge_tags",
            ["name", "chatbot_id"],
        )

    # Clear existing facts and tags — test data only, user approved.
    op.execute("DELETE FROM knowledge_fact_tags")
    op.execute("DELETE FROM knowledge_facts")
    op.execute("DELETE FROM knowledge_tags")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "ALTER TABLE knowledge_tags DROP CONSTRAINT IF EXISTS uq_knowledge_tag_name_chatbot"
        )
    )
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_tags_chatbot_id"))
    conn.execute(
        sa.text("ALTER TABLE knowledge_tags DROP COLUMN IF EXISTS chatbot_id")
    )
    conn.execute(
        sa.text(
            "ALTER TABLE knowledge_tags ADD CONSTRAINT uq_knowledge_tag_name UNIQUE (name)"
        )
    )
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_facts_chatbot_id"))
    conn.execute(
        sa.text("ALTER TABLE knowledge_facts DROP COLUMN IF EXISTS chatbot_id")
    )
