"""Drop old columns from ``knowledge_facts`` — idempotent, multi-schema safe.

The columns ``section``, ``date_recorded``, and ``is_deleted`` were removed
from the Python model but still exist in database tables created by earlier
migrations.  This migration drops them **only if they still exist**, so it
works on:

- The ``public`` schema (where older copies of this migration may already
  have dropped ``section`` but not the other two).
- Tenant schemas created after the model changed (the columns were never
  created by ``create_all``, so ``DROP IF EXISTS`` is a no-op).
- Tenant schemas created before the model changed (all three columns
  exist and need to be dropped).

Revision ID: be9c1a2d3e50
Revises: be9c1a2d3e4f
Create Date: 2026-06-14 16:59:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "be9c1a2d3e50"
down_revision: Union[str, None] = "be9c1a2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Return whether *column* exists in *table* for the current connection."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    names = [col["name"] for col in inspector.get_columns(table)]
    return column in names


def upgrade() -> None:
    for col in ("section", "date_recorded", "is_deleted"):
        if _column_exists("knowledge_facts", col):
            op.drop_column("knowledge_facts", col)


def downgrade() -> None:
    # Best-effort restore — only adds columns that are missing.
    defaults = {"section": "Notes", "date_recorded": None, "is_deleted": False}
    for col, default_val in defaults.items():
        if not _column_exists("knowledge_facts", col):
            op.add_column(
                "knowledge_facts",
                sa.Column(
                    col,
                    sa.String() if col == "section" else sa.Boolean(),
                    nullable=True,
                ),
            )
