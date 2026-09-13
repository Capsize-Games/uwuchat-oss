"""Retired billing migration retained for revision-chain compatibility."""

revision: str = "f2b3c13e6a1m"
down_revision: str = "f2b3c13e6a1l"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Billing columns are supplied by the private billing extension."""


def downgrade() -> None:
    """Nothing to remove from the OSS schema."""
