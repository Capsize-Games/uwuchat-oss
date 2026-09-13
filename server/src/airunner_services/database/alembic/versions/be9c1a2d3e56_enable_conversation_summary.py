"""Enable conversation summary by default.

The column was created with default=False but the application default has
always been True.  Flip existing rows so summarization activates without
requiring a manual settings change.

Revision ID: be9c1a2d3e56
Revises: be9c1a2d3e55
Create Date: 2026-06-15
"""

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "be9c1a2d3e56"
down_revision: Union[str, None] = "be9c1a2d3e55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE llm_generator_settings"
            " SET perform_conversation_summary = TRUE"
            " WHERE perform_conversation_summary IS FALSE"
            "    OR perform_conversation_summary IS NULL"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE llm_generator_settings"
            " SET perform_conversation_summary = FALSE"
        )
    )
