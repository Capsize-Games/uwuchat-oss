"""Idempotency helpers for the auth extension's Alembic migrations.

The ``accounts`` table lives in the **public** schema and is shared across
all tenants. During multi-tenant provisioning, ``setup_database()`` runs the
full migration set against each new tenant schema, and Alembic can traverse
the auth revision more than once in a single ``upgrade("heads")`` pass
(multiple disconnected roots — core + extension — sharing one upgrade). That
makes a naive ``op.create_table("accounts")`` fail with ``DuplicateTable`` and
aborts provisioning, leaving the tenant schema empty.

Guarding each migration with these existence checks makes the auth chain
safe to (re-)apply: a second pass becomes a no-op instead of an error. The
checks read the live bind, so they see DDL committed earlier in the same
transaction (Postgres) and reflect the real current schema.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


def has_table(table_name: str) -> bool:
    """Return True when *table_name* exists in the bind's current schema."""
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name)


def has_column(table_name: str, column_name: str) -> bool:
    """Return True when *table_name* already has *column_name*."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table_name):
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


__all__ = ["has_table", "has_column"]
