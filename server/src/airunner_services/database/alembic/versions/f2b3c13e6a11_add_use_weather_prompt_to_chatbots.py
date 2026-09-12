"""Add use_weather_prompt column to chatbots and enable for system bots.

Revision ID: f2b3c13e6a11
Revises: f2b3c13e6a10
Create Date: 2026-06-30
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a11"
down_revision: Union[str, None] = "f2b3c13e6a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def upgrade() -> None:
    """Add use_weather_prompt and enable it for system bots."""
    if not _column_exists("chatbots", "use_weather_prompt"):
        op.add_column(
            "chatbots",
            sa.Column(
                "use_weather_prompt",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    # Enable weather for any existing system bot
    chatbots = sa.table(
        "chatbots",
        sa.column("id", sa.Integer),
        sa.column("is_system_bot", sa.Boolean),
        sa.column("use_weather_prompt", sa.Boolean),
    )
    op.execute(
        chatbots.update()
        .where(chatbots.c.is_system_bot.is_(True))
        .values(use_weather_prompt=True)
    )


def downgrade() -> None:
    """Remove use_weather_prompt column."""
    op.drop_column("chatbots", "use_weather_prompt")
