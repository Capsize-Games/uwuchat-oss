"""Drop ``date_recorded`` and ``is_deleted`` from ``knowledge_facts`` if they
still exist.

The earlier revision ``be9c1a2d3e50`` was retro-fitted to handle all old
columns, but schemas that already applied the first version of that
migration (which only dropped ``section``) still carry ``date_recorded``
and ``is_deleted``.  This migration cleans those up wherever they remain.

Revision ID: be9c1a2d3e51
Revises: be9c1a2d3e50
Create Date: 2026-06-14 17:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "be9c1a2d3e51"
down_revision: Union[str, None] = "be9c1a2d3e50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Return whether *column* exists in *table* for the current connection."""
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    names = [col["name"] for col in inspector.get_columns(table)]
    return column in names


def upgrade() -> None:
    for col in ("date_recorded", "is_deleted"):
        if _column_exists("knowledge_facts", col):
            op.drop_column("knowledge_facts", col)


def downgrade() -> None:
    for col in ("date_recorded", "is_deleted"):
        if not _column_exists("knowledge_facts", col):
            op.add_column(
                "knowledge_facts",
                sa.Column(col, sa.Boolean(), nullable=True),
            )
