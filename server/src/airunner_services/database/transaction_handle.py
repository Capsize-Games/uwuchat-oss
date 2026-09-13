"""Transaction handle for multi-step database operations.

Yielded by ``Model.objects.transaction()``, this wraps the active
``session_scope()`` session and provides ``add``, ``add_all``,
``delete``, ``query``, and ``execute``.

Usage::

    with KnowledgeFact.objects.transaction() as tx:
        tx.add(KnowledgeFact(fact_text="..."))
        tx.add_all([KnowledgeFact(...), KnowledgeFact(...)])
        tx.flush()   # optional — push to DB without committing
    # ← committed on exit, rolled back on exception

    with LLMGeneratorSettings.objects.transaction() as tx:
        settings = tx.query(LLMGeneratorSettings).first()
        if settings.conversation_id != target:
            settings.conversation_id = target
            tx.add(settings)
"""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy.orm import Query, Session
from sqlalchemy.sql import Executable


class TransactionHandle:
    """Thin wrapper around the active session_scope() session.

    The session's lifecycle is managed by the surrounding
    ``session_scope()`` context manager — commit on success,
    rollback on exception.  Callers should never call ``commit()``
    or ``rollback()`` directly on this handle.
    """

    def __init__(self, session: Session) -> None:
        """Wrap *session*."""
        self.session = session

    def add(self, instance: Any) -> None:
        """Add one ORM instance to the session."""
        self.session.add(instance)

    def add_all(self, instances: List[Any]) -> None:
        """Add a list of ORM instances to the session."""
        self.session.add_all(instances)

    def delete(self, instance: Any) -> None:
        """Mark one ORM instance for deletion."""
        self.session.delete(instance)

    def flush(self) -> None:
        """Push pending changes to the database without committing."""
        self.session.flush()

    def query(self, *entities: Any) -> Query:
        """Return a SQLAlchemy Query on this transaction's session.

        Callers must consume the result within the ``with`` block.
        """
        return self.session.query(*entities)

    def execute(
        self,
        statement: Executable,
        params: Optional[dict] = None,
    ) -> Any:
        """Execute a raw SQL statement within this transaction."""
        if params:
            return self.session.execute(statement, params)
        return self.session.execute(statement)
