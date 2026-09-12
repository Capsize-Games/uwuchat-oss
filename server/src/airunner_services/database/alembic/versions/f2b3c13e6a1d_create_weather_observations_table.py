"""Create weather_observations table (public schema).

Stores anonymous, cross-tenant historical weather observations with no
PII and no foreign keys to any user/account/chatbot table.

Revision ID: f2b3c13e6a1d
Revises: f2b3c13e6a1c
Create Date: 2026-07-10
"""

from __future__ import annotations

import datetime

import sqlalchemy as sa
from alembic import op
from typing import Sequence, Union

revision: str = "f2b3c13e6a1d"
down_revision: Union[str, None] = "f2b3c13e6a1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str, schema: str = "public") -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names(schema=schema)


def _base_columns():
    """Return the standard BaseModel columns applied to every table."""
    return [
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=True,
            default=datetime.datetime.utcnow,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=True,
            default=datetime.datetime.utcnow,
            onupdate=datetime.datetime.utcnow,
        ),
        sa.Column(
            "deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    ]


def upgrade() -> None:
    """Create the weather_observations table if it does not exist."""
    if not _table_exists("weather_observations"):
        op.create_table(
            "weather_observations",
            sa.Column(
                "id",
                sa.Integer(),
                primary_key=True,
                autoincrement=True,
            ),
            sa.Column(
                "observed_at",
                sa.DateTime(timezone=True),
                nullable=False,
            ),
            sa.Column(
                "latitude",
                sa.Float(),
                nullable=False,
            ),
            sa.Column(
                "longitude",
                sa.Float(),
                nullable=False,
            ),
            sa.Column(
                "temperature",
                sa.Float(),
                nullable=True,
            ),
            sa.Column(
                "precipitation",
                sa.Float(),
                nullable=True,
            ),
            sa.Column(
                "rain",
                sa.Float(),
                nullable=True,
            ),
            sa.Column(
                "snowfall",
                sa.Float(),
                nullable=True,
            ),
            sa.Column(
                "wind_speed",
                sa.Float(),
                nullable=True,
            ),
            sa.Column(
                "wind_gusts",
                sa.Float(),
                nullable=True,
            ),
            sa.Column(
                "weather_code",
                sa.Integer(),
                nullable=True,
            ),
            sa.Column(
                "unit_system",
                sa.String(16),
                nullable=True,
            ),
            sa.Column(
                "source",
                sa.String(64),
                nullable=False,
                server_default=sa.text("'open-meteo'"),
            ),
            *_base_columns(),
            schema="public",
        )


def downgrade() -> None:
    """Drop the weather_observations table."""
    op.drop_table("weather_observations", schema="public")
