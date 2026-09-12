"""Encrypt plaintext API key columns with UserEncryptedText.

Revision ID: f2b3c13e6a24
Revises: f2b3c13e6a23
Create Date: 2026-07-30

Converts five plaintext String columns storing third-party bearer
credentials to UserEncryptedText (impl=Text) for encryption-at-rest:

  llm_generator_settings.api_key
  application_settings.hf_api_key_read_key
  application_settings.hf_api_key_write_key
  application_settings.civit_ai_api_key
  application_settings.openai_api_key

Existing plaintext values are preserved (UserEncryptedText passes
them through on read if they don't look like ciphertext).  They will
be re-encrypted on next write through the ORM.

Edge/local desktop deployments are safe: these columns are never
read or written in edge-only code paths (application_settings API
keys have zero edge references; llm_generator_settings.api_key is
only read, never written, in edge workers, and legacy plaintext
passes through process_result_value unchanged).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2b3c13e6a24"
down_revision = "f2b3c13e6a23"
branch_labels = None
depends_on = None


def _column_type(table: str, column: str) -> str | None:
    """Return the type name of *column* in *table*, or None."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return None
    for col in inspector.get_columns(table):
        if col["name"] == column:
            return str(col["type"]).upper().split("(")[0].strip()
    return None


def upgrade() -> None:
    _convert("llm_generator_settings", "api_key")
    _convert("application_settings", "hf_api_key_read_key")
    _convert("application_settings", "hf_api_key_write_key")
    _convert("application_settings", "civit_ai_api_key")
    _convert("application_settings", "openai_api_key")


def _convert(table: str, column: str) -> None:
    type_name = _column_type(table, column)
    if type_name is None:
        return
    if type_name not in ("TEXT",):
        op.alter_column(
            table,
            column,
            existing_type=sa.String(),
            type_=sa.Text(),
            existing_nullable=True,
            postgresql_using=f"{column}::text",
        )


def downgrade() -> None:
    """Revert columns to String.

    Note: reverting does NOT decrypt data — it only changes the
    column type back.  Encrypted values will remain in the column as
    opaque ciphertext strings.  This is intentionally lossy on
    downgrade.
    """
    _revert("llm_generator_settings", "api_key")
    _revert("application_settings", "hf_api_key_read_key")
    _revert("application_settings", "hf_api_key_write_key")
    _revert("application_settings", "civit_ai_api_key")
    _revert("application_settings", "openai_api_key")


def _revert(table: str, column: str) -> None:
    type_name = _column_type(table, column)
    if type_name == "TEXT":
        op.alter_column(
            table,
            column,
            existing_type=sa.Text(),
            type_=sa.String(),
            existing_nullable=True,
        )
