"""Retired billing migration retained for revision-chain compatibility."""

revision = "auth_005"
down_revision = "auth_004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Billing is supplied by an optional private extension."""


def downgrade() -> None:
    """Nothing to remove from the OSS schema."""
