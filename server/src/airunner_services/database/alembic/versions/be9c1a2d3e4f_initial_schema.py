"""Initial schema — creates all tables from current model definitions.

Revision ID: be9c1a2d3e4f
Revises:
Create Date: 2026-06-13 16:40:00.000000

"""

import importlib
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "be9c1a2d3e4f"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tenant_schema_for_key(key: str) -> str:
    return f"tenant_{key}"


def _seed_dev_accounts() -> None:
    """Create dev accounts when DEV_ENV is set."""
    from airunner_services.settings import DEV_ENV

    if not DEV_ENV:
        return

    from extensions.auth.server.passwords import hash_password

    bind = op.get_bind()
    # Check if any accounts already exist (idempotent).
    existing = bind.execute(sa.text("SELECT 1 FROM accounts LIMIT 1")).first()
    if existing:
        return

    dev_accounts = [
        {
            "email": "admin@example.com",
            "username": "admin",
            "password": "admin123",
            "is_superuser": True,
            "is_verified": True,
        },
        {
            "email": "user@example.com",
            "username": "user",
            "password": "user1234",
            "is_superuser": False,
            "is_verified": True,
        },
    ]

    for acc in dev_accounts:
        raw_key = f"{uuid.uuid4().hex[:12]}_{acc['username'].lower()}"
        schema = _tenant_schema_for_key(raw_key)
        bind.execute(
            sa.text(
                "INSERT INTO accounts "
                "(email, username, password_hash, is_active, "
                "is_verified, is_superuser, tenant_schema, "
                "auth_provider, token_version, deleted) "
                "VALUES "
                "(:email, :username, :pw, true, "
                ":verified, :super, :schema, "
                "'local', 0, false)"
            ),
            {
                "email": acc["email"],
                "username": acc["username"],
                "pw": hash_password(acc["password"]),
                "verified": acc["is_verified"],
                "super": acc["is_superuser"],
                "schema": schema,
            },
        )


def upgrade() -> None:
    # Ensure pgvector extension exists for KnowledgeFact embeddings.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Import all model modules so they register with Base.metadata.
    importlib.import_module("airunner_services.database.models")
    importlib.import_module("extensions.auth.server.models")

    from airunner_services.database.base import Base
    from sqlalchemy import inspect as sa_inspect, text

    bind = op.get_bind()
    inspector = sa_inspect(bind)

    # Determine the schema this migration is materializing. Inspect it
    # EXPLICITLY: has_table()/default get_table_names() respect the search_path
    # and would treat a table living in the ``public`` fallback as already
    # present, leaving a tenant schema empty and silently routing all data to
    # public.
    current_schema = bind.execute(text("SELECT current_schema()")).scalar()
    existing = set(inspector.get_table_names(schema=current_schema))

    tables = list(Base.metadata.sorted_tables)
    if current_schema != "public":
        # Inside a tenant schema, never materialize ``__public_schema__`` tables
        # (e.g. the shared auth ``accounts`` table). An empty tenant copy would
        # shadow the real public row store and break tenant resolution.
        public_only = {
            mapper.local_table.name
            for mapper in Base.registry.mappers
            if getattr(mapper.class_, "__public_schema__", False)
            and mapper.local_table is not None
        }
        tables = [t for t in tables if t.name not in public_only]

    missing = [t for t in tables if t.name not in existing]
    if missing:
        Base.metadata.create_all(bind=bind, tables=missing, checkfirst=False)

    # Seed dev accounts when DEV_ENV=1.
    _seed_dev_accounts()


def downgrade() -> None:
    importlib.import_module("airunner_services.database.models")
    importlib.import_module("extensions.auth.server.models")

    from airunner_services.database.base import Base

    Base.metadata.drop_all(bind=op.get_bind())
