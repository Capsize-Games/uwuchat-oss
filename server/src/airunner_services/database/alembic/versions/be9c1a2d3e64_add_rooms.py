"""Retain the historical rooms revision after world extraction.

Revision ID: be9c1a2d3e64
Revises: be9c1a2d3e63
Create Date: 2026-06-16
"""

revision: str = "be9c1a2d3e64"
down_revision = "be9c1a2d3e63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: world-social owns these tables in the private repo."""
    return None


def downgrade() -> None:
    """No-op: historical data must remain intact."""
    return None
