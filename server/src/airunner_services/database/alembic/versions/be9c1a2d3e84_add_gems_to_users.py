"""Retain the historical gems revision after economy extraction.

Revision ID: be9c1a2d3e84
Revises: be9c1a2d3e83
Create Date: 2026-06-20
"""

revision = "be9c1a2d3e84"
down_revision = "be9c1a2d3e83"
branch_labels = None
depends_on = None


def upgrade():
    """No-op: economy owns this schema in the private repo."""
    return None


def downgrade():
    """No-op: historical data must remain intact."""
    return None
