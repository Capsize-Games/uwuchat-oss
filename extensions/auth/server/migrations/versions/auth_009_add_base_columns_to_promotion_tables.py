"""Retired promotion migration retained for revision-chain compatibility."""

revision = "auth_009"
down_revision = "auth_008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """The retired promotion tables are absent from the OSS schema."""


def downgrade() -> None:
    """Nothing to remove from the OSS schema."""
