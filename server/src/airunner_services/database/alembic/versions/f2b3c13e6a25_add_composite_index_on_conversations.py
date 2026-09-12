"""Add composite index on conversations(chatbot_id, id DESC).

Revision ID: f2b3c13e6a25
Revises: 07bdf7773f84
Create Date: 2026-08-04 09:30:00.000000

``SessionManager.load_thread()`` filters conversations by chatbot_id and
orders by id DESC (windowed at 20 rows per chatbot).  A composite index
on (chatbot_id, id DESC) serves that access path directly; a plain index
on chatbot_id alone would still require a per-chatbot sort of the whole
conversation list.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a25"
down_revision: Union[str, None] = "07bdf7773f84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = "ix_conversations_chatbot_id_id_desc"


def _table_exists(table: str) -> bool:
    """Probe whether a table exists (search_path-aware)."""
    conn = op.get_bind()
    return bool(
        conn.execute(sa.text(f"SELECT to_regclass('{table}')")).scalar()
    )


def _index_exists(table: str, index: str) -> bool:
    """Probe whether an index exists in the target schema."""
    conn = op.get_bind()
    return index in [i["name"] for i in sa.inspect(conn).get_indexes(table)]


def upgrade() -> None:
    if not _table_exists("conversations"):
        return
    if not _index_exists("conversations", _INDEX_NAME):
        op.create_index(
            _INDEX_NAME,
            "conversations",
            [sa.text("chatbot_id"), sa.text("id DESC")],
            unique=False,
        )


def downgrade() -> None:
    if _table_exists("conversations") and _index_exists(
        "conversations", _INDEX_NAME
    ):
        op.drop_index(_INDEX_NAME, table_name="conversations")
