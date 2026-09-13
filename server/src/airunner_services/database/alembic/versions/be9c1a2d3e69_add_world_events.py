"""Add world_events table for shared observable world state.

Revision ID: be9c1a2d3e69
Revises: be9c1a2d3e68
Create Date: 2026-06-16
"""

revision: str = "be9c1a2d3e69"
down_revision = "be9c1a2d3e68"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: world-social owns this table in the private repo."""
    return None


def downgrade() -> None:
    """No-op: historical data must remain intact."""
    return None
