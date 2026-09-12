"""Encrypt EmailMessage PII columns with UserEncryptedText.

Revision ID: f2b3c13e6a22
Revises: f2b3c13e6a21
Create Date: 2026-07-30

Converts from_address, from_name, to_addresses, cc_addresses, and
subject from plaintext String / JSONB to UserEncryptedText (impl=Text).
to_addresses and cc_addresses are JSON lists serialized as text before
encryption, matching the pattern used for Conversation.value.

This follows the same probe-before-DDL pattern established in
be9c1a2d3e89_switch_encrypted_columns_to_user_encrypted_text.py.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2b3c13e6a22"
down_revision = "f2b3c13e6a21"
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
    """Switch five EmailMessage columns from plaintext to TEXT."""
    columns = [
        "from_address",
        "from_name",
        "to_addresses",
        "cc_addresses",
        "subject",
    ]
    for col_name in columns:
        type_name, nullable = _column_info("email_messages", col_name)
        if type_name is None:
            continue
        if type_name not in ("TEXT",):
            op.alter_column(
                "email_messages",
                col_name,
                existing_type=sa.Text(),
                type_=sa.Text(),
                existing_nullable=nullable,
                postgresql_using=f"{col_name}::text",
            )


def downgrade() -> None:
    """Revert columns to their original types.

    Note: reverting does NOT decrypt data — it only changes the column
    type back.  Encrypted values will remain in the column as opaque
    ciphertext strings.  This is intentionally lossy on downgrade; the
    encryption is meant to be forward-only.
    """
    varchar_cols = ["from_address", "from_name", "subject"]
    jsonb_cols = ["to_addresses", "cc_addresses"]

    for col_name in varchar_cols:
        type_name, nullable = _column_info("email_messages", col_name)
        if type_name == "TEXT":
            op.alter_column(
                "email_messages",
                col_name,
                existing_type=sa.Text(),
                type_=sa.String(255),
                existing_nullable=nullable,
            )

    for col_name in jsonb_cols:
        type_name, nullable = _column_info("email_messages", col_name)
        if type_name == "TEXT":
            op.alter_column(
                "email_messages",
                col_name,
                existing_type=sa.Text(),
                type_=sa.JSONB(),
                existing_nullable=nullable,
                postgresql_using=f"{col_name}::jsonb",
            )
