"""Stub for revision 006 — phantom present in DB but missing on disk.

This file exists solely so Alembic can resolve the revision ID.
No DDL is executed here.

Revision ID: 006
Revises: (none — treated as an independent root branch)
"""

from __future__ import annotations

revision = "006"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
