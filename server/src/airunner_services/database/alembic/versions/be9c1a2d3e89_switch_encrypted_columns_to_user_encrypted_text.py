"""Switch conversations.value and summaries.content to TEXT for UserEncryptedText.

Revision ID: be9c1a2d3e89
Revises: f2b3c13e6a19
Create Date: 2026-07-05

conversations.value was JSON → now uses UserEncryptedText (impl=Text).
Fernet ciphertext is not valid JSON, so the column must be TEXT not JSONB.

summaries.content was String (VARCHAR) → now uses UserEncryptedText
(impl=Text).  Fernet ciphertext can be much longer than VARCHAR, so
the column must be widened to TEXT.

conversations.summary was already Text → UserEncryptedText (impl=Text),
so no type change is needed for that column.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "be9c1a2d3e89"
down_revision = "f2b3c13e6a19"
branch_labels = None
depends_on = None


def _column_info(table: str, column: str):
    """Return (type_name, is_nullable) or (None, None) if missing."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return None, None
    for col in inspector.get_columns(table):
        if col["name"] == column:
            return (
                str(col["type"]).upper().split("(")[0].strip(),
                col.get("nullable", True),
            )
    return None, None


def upgrade() -> None:
    # conversations.value: JSON/JSONB → TEXT
    type_name, nullable = _column_info("conversations", "value")
    if type_name and type_name not in ("TEXT",):
        op.alter_column(
            "conversations",
            "value",
            existing_type=sa.Text() if type_name == "JSON" else None,
            type_=sa.Text(),
            existing_nullable=nullable,
            postgresql_using="value::text",
        )

    # summaries.content: VARCHAR → TEXT
    type_name, nullable = _column_info("summaries", "content")
    if type_name and type_name not in ("TEXT",):
        op.alter_column(
            "summaries",
            "content",
            existing_type=sa.String(),
            type_=sa.Text(),
            existing_nullable=nullable,
        )


def downgrade() -> None:
    # Revert summaries.content: TEXT → VARCHAR
    type_name, nullable = _column_info("summaries", "content")
    if type_name == "TEXT":
        op.alter_column(
            "summaries",
            "content",
            existing_type=sa.Text(),
            type_=sa.String(),
            existing_nullable=nullable,
        )

    # Revert conversations.value: TEXT → JSON
    type_name, nullable = _column_info("conversations", "value")
    if type_name == "TEXT":
        op.alter_column(
            "conversations",
            "value",
            existing_type=sa.Text(),
            type_=sa.JSON(),
            existing_nullable=nullable,
            postgresql_using="value::jsonb",
        )
