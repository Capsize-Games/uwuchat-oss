"""Create headlesscode project, session, and session-event tables.

Revision ID: f2b3c13e6a26
Revises: f2b3c13e6a25
Create Date: 2026-08-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "f2b3c13e6a26"
down_revision: Union[str, None] = "f2b3c13e6a25"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    """Return whether *table* exists in the current schema."""
    inspector = sa.inspect(op.get_bind())
    return table in inspector.get_table_names()


def _create_projects_table() -> None:
    """Create ``headlesscode_projects`` when missing."""
    if _table_exists("headlesscode_projects"):
        return
    op.create_table(
        "headlesscode_projects",
        sa.Column("id", sa.Integer(), autoincrement=True,
                  nullable=False),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("users.id"), nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("repo_path", sa.String(512), nullable=False),
        sa.Column("workspace_root", sa.String(512), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("deleted", sa.Boolean(), server_default=sa.false(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_headlesscode_projects_user_id", "user_id"),
    )


def _create_sessions_table() -> None:
    """Create ``headlesscode_sessions`` when missing."""
    if _table_exists("headlesscode_sessions"):
        return
    op.create_table(
        "headlesscode_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True,
                  nullable=False),
        sa.Column(
            "project_id", sa.Integer(),
            sa.ForeignKey("headlesscode_projects.id"), nullable=False,
        ),
        sa.Column(
            "chatbot_id", sa.Integer(),
            sa.ForeignKey("chatbots.id"), nullable=True,
        ),
        sa.Column(
            "conversation_id", sa.Integer(),
            sa.ForeignKey("conversations.id"), nullable=True,
        ),
        sa.Column(
            "headlesscode_session_id", sa.String(64), nullable=False,
        ),
        sa.Column(
            "status", sa.String(32), nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("task_description", sa.Text(), nullable=True),
        sa.Column("mode", sa.String(64), nullable=True),
        sa.Column(
            "event_offset", sa.Integer(), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("deleted", sa.Boolean(), server_default=sa.false(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_headlesscode_sessions_project_id", "project_id"),
        sa.Index(
            "ix_headlesscode_sessions_headlesscode_session_id",
            "headlesscode_session_id",
        ),
    )


def _create_events_table() -> None:
    """Create ``headlesscode_session_events`` when missing."""
    if _table_exists("headlesscode_session_events"):
        return
    op.create_table(
        "headlesscode_session_events",
        sa.Column("id", sa.Integer(), autoincrement=True,
                  nullable=False),
        sa.Column(
            "session_id", sa.Integer(),
            sa.ForeignKey("headlesscode_sessions.id"), nullable=False,
        ),
        sa.Column("raw_event", JSONB(), nullable=False),
        sa.Column("chat_block_kind", sa.String(16), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("deleted", sa.Boolean(), server_default=sa.false(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.Index("ix_headlesscode_session_events_session_id",
                 "session_id"),
    )


def upgrade() -> None:
    """Create the headlesscode tables idempotently."""
    _create_projects_table()
    _create_sessions_table()
    _create_events_table()


def downgrade() -> None:
    """Drop the headlesscode tables if present."""
    if _table_exists("headlesscode_session_events"):
        op.drop_table("headlesscode_session_events")
    if _table_exists("headlesscode_sessions"):
        op.drop_table("headlesscode_sessions")
    if _table_exists("headlesscode_projects"):
        op.drop_table("headlesscode_projects")
