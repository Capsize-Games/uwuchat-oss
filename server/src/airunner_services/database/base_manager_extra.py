"""Extra query builder and batch operations for RealBaseManager."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.orm import Query

if TYPE_CHECKING:
    from airunner_services.database.managed_query import ManagedQuery


class BaseManagerExtraMixin:
    """Extra batch and query-builder methods for RealBaseManager."""

    cls: Any
    logger: Any

    def filter_first(self, *args) -> Optional[list]:
        """Return the first row matching arbitrary filters."""
        from airunner_services.database.session import session_scope

        with session_scope() as session:
            try:
                result = session.query(self.cls).filter(*args).first()
                session.expunge_all()
                return result.to_dataclass() if result else None
            except Exception as exc:
                self.logger.error("Error in filter(%s): %s", args, exc)
                return None

    def filter_by_first(
        self,
        eager_load: Optional[list[str]] = None,
        **kwargs,
    ) -> Optional[list]:
        """Return the first row matching equality filters."""
        from airunner_services.database.session import session_scope
        from sqlalchemy.orm import joinedload

        with session_scope() as session:
            try:
                query = session.query(self.cls)
                if eager_load:
                    for relationship in eager_load:
                        try:
                            query = query.options(
                                joinedload(getattr(self.cls, relationship)),
                            )
                        except AttributeError:
                            self.logger.warning(
                                "Class %s does not have relationship %s",
                                self.cls.__name__,
                                relationship,
                            )
                result = query.filter_by(**kwargs).first()
                session.expunge_all()
                return result.to_dataclass() if result else None
            except Exception as exc:
                self.logger.error(
                    "Error in filter_by(%s): %s",
                    kwargs,
                    exc,
                )
                return None

    def filter(self, *args) -> Optional[list]:
        """Return all rows matching arbitrary filters."""
        from airunner_services.database.session import session_scope

        with session_scope() as session:
            try:
                result = session.query(self.cls).filter(*args).all()
                session.expunge_all()
                return [obj.to_dataclass() for obj in result]
            except Exception as exc:
                self.logger.error("Error in filter(%s): %s", args, exc)
                return None

    def order_by(self, *args) -> Optional[Query]:
        """Return an ordered query (rarely used directly)."""
        from airunner_services.database.session import session_scope

        with session_scope() as session:
            try:
                result = session.query(self.cls).order_by(*args)
                session.expunge_all()
                return result
            except Exception as exc:
                self.logger.error("Error in order_by(%s): %s", args, exc)
                return None

    def options(self, *args) -> Optional[Query]:
        """Return a query with loader options applied."""
        from airunner_services.database.session import session_scope

        with session_scope() as session:
            try:
                result = session.query(self.cls).options(*args)
                session.expunge_all()
                return result
            except Exception as exc:
                self.logger.error("Error in options(%s): %s", args, exc)
                return None

    def delete_all(self) -> int:
        """Delete all rows and return the count removed."""
        from airunner_services.database.session import session_scope

        with session_scope() as session:
            try:
                result = session.query(self.cls).delete()
                session.commit()
                return result
            except Exception as exc:
                self.logger.error("Error in delete(): %s", exc)
                return 0

    def delete_by(self, **kwargs) -> bool:
        """Delete rows matching equality filters."""
        from airunner_services.database.session import session_scope

        with session_scope() as session:
            try:
                result = session.query(self.cls).filter_by(**kwargs).delete()
                session.commit()
                return bool(result)
            except Exception as exc:
                self.logger.error("Error in delete_by(%s): %s", kwargs, exc)
                return False

    # ── Fluent query builder + transaction (new API) ────────────────

    def query(self, *entities: Any) -> "ManagedQuery":
        """Return a fluent query builder for this model."""
        from airunner_services.database.managed_query import (
            ManagedQuery,
        )

        return ManagedQuery(self.cls, entities)

    @contextmanager
    def transaction(self):
        """Yield a TransactionHandle for multi-step operations."""
        from airunner_services.database.session import session_scope
        from airunner_services.database.transaction_handle import (
            TransactionHandle,
        )

        with session_scope() as session:
            yield TransactionHandle(session)


def _save_instance(mgr, instance) -> bool:
    """Persist an existing ORM instance."""
    from airunner_services.database.session import session_scope

    with session_scope() as session:
        try:
            session.add(instance)
            session.commit()
            session.refresh(instance)
            session.expunge(instance)
            return True
        except Exception as exc:
            mgr.logger.error("Error in save(): %s", exc)
            return False


def _delete_instance(mgr, instance) -> bool:
    """Delete an ORM instance from the database."""
    from airunner_services.database.session import session_scope

    with session_scope() as session:
        try:
            session.delete(instance)
            session.commit()
            return True
        except Exception as exc:
            mgr.logger.error("Error in delete(): %s", exc)
            return False
