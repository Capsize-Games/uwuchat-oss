"""Retired billing repair migration retained for chain compatibility."""

revision = "auth_013"
down_revision = "auth_012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """The retired billing tables are absent from the OSS schema."""


def downgrade() -> None:
    """Nothing to remove from the OSS schema."""
