"""In-process registry for per-resource security guards.

RPC settings handlers (``rpc_settings.py``) call into this registry
before applying create / update / delete / reset-defaults operations
**and** before returning serialized rows to the client on the read
path.  A guard registered for a resource can:

* Silently strip or force field values on create/update.
* Raise ``ResourceGuardRejected`` to block an operation with a 403
  response.
* Narrow the fields returned to non-superuser clients (``filter_read``).

When no guard is registered for a resource, behaviour is byte-for-byte
identical to the pre-guard code — all operations proceed unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ResourceGuardRejected(Exception):
    """Raised by a guard to block an operation with a 403 response."""

    def __init__(self, message: str = "Operation not permitted.") -> None:
        super().__init__(message)
        self.message = message


@dataclass
class ResourceGuard:
    """Optional hooks a project can implement for a resource type.

    Every hook is optional — a guard only needs to define the hooks
    it wants to enforce.  Missing hooks are silently skipped.
    """

    resource_name: str

    def sanitize_create(
        self, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Called before creating a new row.  Return (possibly modified)
        values dict.  The guard may force fields to server-chosen values
        or strip keys the client must never set at creation time.

        ``is_superuser`` is passed as a keyword argument when the calling
        handler can determine the authenticated user's role.
        """
        return values

    def sanitize_update(
        self, item: Any, values: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]:
        """Called before updating an existing row (by-id or singleton).
        ``item`` is the already-fetched ORM row.  Return the (possibly
        modified) values dict.

        ``is_superuser`` is passed as a keyword argument when the calling
        handler can determine the authenticated user's role.
        """
        return values

    def before_delete(self, item: Any, **kwargs: Any) -> None:
        """Called before ``tx.delete(item)``.  Raise
        ``ResourceGuardRejected`` to block the deletion.

        ``is_superuser`` is passed as a keyword argument when the calling
        handler can determine the authenticated user's role.
        """

    def before_reset_defaults(self, item: Any) -> None:
        """Called before resetting a row to column defaults.  Raise
        ``ResourceGuardRejected`` to block the operation.
        """

    def check_ownership(
        self, item: Any, account_id: int | None, is_superuser: bool
    ) -> None:
        """Called before update-by-id or delete.  Raise
        ``ResourceGuardRejected`` if *item* does not belong to the
        caller.

        Default: no check (framework passthrough) — a resource with no
        ownership concept (e.g. shared/global config) does not need
        this; a guard only needs to override it if the resource is
        account-scoped.
        """

    def filter_read(
        self, record: dict[str, Any], is_superuser: bool
    ) -> dict[str, Any]:
        """Called after a row is serialized for any read response
        (singleton GET, query, first, and the write-echo responses).
        Return the (possibly narrowed) dict the client will receive.
        Default: return the record unchanged — a guard only needs to
        override this if it wants to restrict what non-superusers see.
        """
        return record

# -- registry ----------------------------------------------------------

_registry: dict[str, ResourceGuard] = {}

# -- exposure allowlist -------------------------------------------------

_exposed_resources: set[str] = set()


def expose_resource(resource_name: str) -> None:
    """Mark *resource_name* as reachable via the generic WS resource
    store.  A resource with no guard AND no exposure entry is not
    reachable at all — see :func:`is_exposed`.
    """
    _exposed_resources.add(resource_name)


def is_exposed(resource_name: str) -> bool:
    """True if *resource_name* may be served by the generic resource
    store.  Registering a guard for a resource implicitly exposes it
    (a guard is meaningless for a resource nothing can reach), so this
    also checks the guard registry.
    """
    return resource_name in _exposed_resources or (
        resource_name in _registry
    )


def register_guard(guard: ResourceGuard) -> None:
    """Register a guard for the resource named in *guard.resource_name*.

    Replaces any previously-registered guard for the same resource.
    """
    _registry[guard.resource_name] = guard


def get_guard(resource_name: str) -> ResourceGuard | None:
    """Return the guard registered for *resource_name*, or ``None``."""
    return _registry.get(resource_name)


def clear_registry() -> None:
    """Remove all registered guards and exposure entries (intended for
    test isolation)."""
    _registry.clear()
    _exposed_resources.clear()
