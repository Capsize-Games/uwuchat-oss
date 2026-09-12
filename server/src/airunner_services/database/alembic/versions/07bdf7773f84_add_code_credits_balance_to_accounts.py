"""Add code_credits_usd to accounts and code_credit_transactions table.

Revision ID: 07bdf7773f84
Revises: f2b3c13e6a24
Create Date: 2026-08-02 22:20:35.299892

UwUChat code-credits: a real-dollar prepaid balance on the public-schema
``accounts`` table (admin-only, manual top-up), plus a per-account debit
ledger that gives idempotency and an audit trail for headlesscode session
spend. Both live in the **public** schema only — never in tenant schemas.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "07bdf7773f84"
down_revision: Union[str, None] = "f2b3c13e6a24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Probe whether a column exists in the target schema."""
    conn = op.get_bind()
    return column in [
        c["name"] for c in sa.inspect(conn).get_columns(table)
    ]


def _table_exists(table: str) -> bool:
    """Probe whether a table exists (search_path-aware)."""
    conn = op.get_bind()
    return bool(
        conn.execute(sa.text(f"SELECT to_regclass('{table}')")).scalar()
    )


def upgrade() -> None:
    if not _column_exists("accounts", "code_credits_usd"):
        op.add_column(
            "accounts",
            sa.Column(
                "code_credits_usd",
                sa.Numeric(10, 4),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    if not _table_exists("code_credit_transactions"):
        op.create_table(
            "code_credit_transactions",
            sa.Column(
                "id", sa.Integer(), autoincrement=True, nullable=False
            ),
            sa.Column("account_id", sa.Integer(), nullable=False),
            sa.Column(
                "amount_usd", sa.Numeric(10, 4), nullable=False
            ),
            sa.Column("kind", sa.String(length=16), nullable=False),
            sa.Column(
                "session_id", sa.String(length=64), nullable=True
            ),
            sa.Column("note", sa.String(length=255), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(
                ["account_id"], ["accounts.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_code_credit_transactions_account_id",
            "code_credit_transactions",
            ["account_id"],
            unique=False,
        )
        op.create_index(
            "ix_code_credit_transactions_session_id",
            "code_credit_transactions",
            ["session_id"],
            unique=False,
        )


def downgrade() -> None:
    if _table_exists("code_credit_transactions"):
        op.drop_table("code_credit_transactions")
    if _column_exists("accounts", "code_credits_usd"):
        op.drop_column("accounts", "code_credits_usd")
