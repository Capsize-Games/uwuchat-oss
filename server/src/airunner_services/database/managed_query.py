"""Fluent query builder that wraps session_scope and the expunge dance.

Usage::

    # Single-model query → returns dataclasses
    rows = Conversation.objects.query().filter(
        Conversation.title.ilike("%foo%"),
    ).order_by(
        Conversation.created_at.desc(),
    ).offset(0).limit(100).all()

    # Multi-entity query → returns Row objects
    rows = KnowledgeFact.objects.query(
        func.date(KnowledgeFact.created_at).label("fact_date"),
        func.count(KnowledgeFact.id),
    ).filter(
        KnowledgeFact.deleted.is_(False),
    ).group_by(
        func.date(KnowledgeFact.created_at),
    ).all()

    # Bulk delete
    count = DocumentChunk.objects.query().filter(
        DocumentChunk.doc_id == doc_id,
    ).delete(synchronize_session=False)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Query
from sqlalchemy.sql.elements import ColumnElement

from airunner_services.database.session import session_scope


class ManagedQuery:
    """Record query builder calls and execute them inside session_scope()."""

    def __init__(
        self,
        model_cls: type,
        entities: Tuple[Any, ...],
    ) -> None:
        """Store the model class and optional entity list."""
        self._model_cls = model_cls
        self._entities: Sequence[Any] = entities if entities else (model_cls,)
        self._filters: List[ColumnElement[bool]] = []
        self._filter_by_kwargs: Dict[str, Any] = {}
        self._order_by_clauses: List[Any] = []
        self._group_by_clauses: List[Any] = []
        self._options: List[Any] = []
        self._offset_val: Optional[int] = None
        self._limit_val: Optional[int] = None
        self._is_distinct: bool = False
        self._having_clauses: List[Any] = []
        self._joins: List[Tuple[Any, Optional[Any]]] = []

    # ── Non-terminal builder methods ────────────────────────────────

    def filter(self, *args: ColumnElement[bool]) -> "ManagedQuery":
        """Add WHERE conditions."""
        self._filters.extend(args)
        return self

    def filter_by(self, **kwargs: Any) -> "ManagedQuery":
        """Add simple equality WHERE conditions."""
        self._filter_by_kwargs.update(kwargs)
        return self

    def order_by(self, *args: Any) -> "ManagedQuery":
        """Add ORDER BY clauses."""
        self._order_by_clauses.extend(args)
        return self

    def group_by(self, *args: Any) -> "ManagedQuery":
        """Add GROUP BY clauses."""
        self._group_by_clauses.extend(args)
        return self

    def having(self, *args: Any) -> "ManagedQuery":
        """Add HAVING conditions."""
        self._having_clauses.extend(args)
        return self

    def offset(self, n: int) -> "ManagedQuery":
        """Set OFFSET."""
        self._offset_val = n
        return self

    def limit(self, n: int) -> "ManagedQuery":
        """Set LIMIT."""
        self._limit_val = n
        return self

    def distinct(self) -> "ManagedQuery":
        """Add DISTINCT."""
        self._is_distinct = True
        return self

    def options(self, *args: Any) -> "ManagedQuery":
        """Add loader options (joinedload, etc.)."""
        self._options.extend(args)
        return self

    def join(self, target: Any, onclause: Any = None) -> "ManagedQuery":
        """Add a JOIN."""
        self._joins.append((target, onclause))
        return self

    def outerjoin(self, target: Any, onclause: Any = None) -> "ManagedQuery":
        """Add an OUTER JOIN."""
        self._joins.append((target, onclause))
        return self

    # ── Internal query builder ──────────────────────────────────────

    def _build_query(self, session) -> Query:
        """Apply all builder state to a fresh Query on *session*."""
        q = session.query(*self._entities)

        for f in self._filters:
            q = q.filter(f)
        if self._filter_by_kwargs:
            q = q.filter_by(**self._filter_by_kwargs)
        for clause in self._order_by_clauses:
            q = q.order_by(clause)
        for clause in self._group_by_clauses:
            q = q.group_by(clause)
        for clause in self._having_clauses:
            q = q.having(clause)
        for target, onclause in self._joins:
            q = q.join(target, onclause)
        if self._is_distinct:
            q = q.distinct()
        if self._offset_val is not None:
            q = q.offset(self._offset_val)
        if self._limit_val is not None:
            q = q.limit(self._limit_val)
        for opt in self._options:
            q = q.options(opt)
        return q

    # ── Terminal methods ────────────────────────────────────────────

    def all(self) -> List[Any]:
        """Execute and return all results.

        When querying a single model class (the default), each row is
        converted to its dataclass via ``to_dataclass()``.  Otherwise
        the raw SQLAlchemy ``Row`` objects are returned.  All ORM
        instances are expunged before returning so that the caller
        never encounters ``DetachedInstanceError``.
        """
        with session_scope() as session:
            q = self._build_query(session)
            rows = q.all()
            session.expunge_all()
            if self._is_single_model_query():
                return [row.to_dataclass() for row in rows]
            return rows

    def first(self) -> Optional[Any]:
        """Execute and return the first result, or None."""
        with session_scope() as session:
            q = self._build_query(session)
            row = q.first()
            if row is None:
                return None
            session.expunge_all()
            if self._is_single_model_query():
                return row.to_dataclass()
            return row

    def one(self) -> Any:
        """Execute and return exactly one result.  Raises if 0 or >1."""
        with session_scope() as session:
            q = self._build_query(session)
            row = q.one()
            session.expunge_all()
            if self._is_single_model_query():
                return row.to_dataclass()
            return row

    def one_or_none(self) -> Optional[Any]:
        """Execute and return one result, or None."""
        with session_scope() as session:
            q = self._build_query(session)
            row = q.one_or_none()
            if row is None:
                return None
            session.expunge_all()
            if self._is_single_model_query():
                return row.to_dataclass()
            return row

    def count(self) -> int:
        """Return the number of rows matching the filters."""
        with session_scope() as session:
            q = self._build_query(session)
            return q.count()

    def scalar(self) -> Any:
        """Return the first column of the first row."""
        with session_scope() as session:
            q = self._build_query(session)
            result = q.scalar()
            return result

    def scalars(self) -> List[Any]:
        """Return the first column of every row as a flat list."""
        with session_scope() as session:
            q = self._build_query(session)
            return [row[0] for row in q.all()]

    def delete(self, synchronize_session: bool = False) -> int:
        """Execute a bulk DELETE and return the row count."""
        with session_scope() as session:
            q = self._build_query(session)
            return q.delete(synchronize_session=synchronize_session)

    def update(
        self,
        values: Dict[str, Any],
        synchronize_session: bool = False,
    ) -> int:
        """Execute a bulk UPDATE and return the row count."""
        with session_scope() as session:
            q = self._build_query(session)
            return q.update(values, synchronize_session=synchronize_session)

    # ── Helpers ─────────────────────────────────────────────────────

    def _is_single_model_query(self) -> bool:
        """Return True when the default (single-model) entity is used."""
        return (
            len(self._entities) == 1 and self._entities[0] is self._model_cls
        )
