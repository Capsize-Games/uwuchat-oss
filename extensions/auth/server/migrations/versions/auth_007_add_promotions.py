"""Retired promotion migration retained for revision-chain compatibility."""

revision = "auth_007"
down_revision = "auth_005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Promotion storage belongs to the private billing extension."""


def downgrade() -> None:
    """Nothing to remove from the OSS schema."""
