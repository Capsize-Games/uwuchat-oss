"""Retired billing migration retained for revision-chain compatibility."""

revision = "auth_012"
down_revision = "auth_011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Chargeback storage belongs to the private billing extension."""


def downgrade() -> None:
    """Nothing to remove from the OSS schema."""
