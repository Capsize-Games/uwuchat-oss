"""Add WorldLoop columns to chatbots table.

Revision ID: be9c1a2d3e63
Revises: be9c1a2d3e62
Create Date: 2026-06-16
"""

revision: str = "be9c1a2d3e63"
down_revision = "be9c1a2d3e62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: chatbot state remains application-owned."""
    return None


def downgrade() -> None:
    """No-op: historical data must remain intact."""
    return None
