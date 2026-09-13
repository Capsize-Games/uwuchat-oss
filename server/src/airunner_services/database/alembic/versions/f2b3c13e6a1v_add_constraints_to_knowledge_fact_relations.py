"""No-op stub.

The FK/schema-resolution theory in earlier revisions of this
docstring was incorrect. The real cause of the observed
ForeignKeyViolation/table-missing symptoms was that
``KnowledgeFactRelation`` was never registered in
``airunner_services.database.models.__all__`` — new tenant schemas
skip full Alembic replay (see ``_run_migrations`` in
setup_migrations.py) and rely on ``_repair_application_schema``'s
``create_all``-based materialization instead, which only creates
tables for models it can discover via that registry. Fixed by adding
the import/``__all__`` entry in ``database/models/__init__.py``. FK
constraints work fine per tenant (see ``f2b3c13e6a1u`` and the model
class) once the table actually exists there. This migration remains a
no-op; it is kept only to preserve the revision chain.
"""
from __future__ import annotations

from typing import Sequence, Union

revision: str = "f2b3c13e6a1v"
down_revision: Union[str, None] = "f2b3c13e6a1u"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
