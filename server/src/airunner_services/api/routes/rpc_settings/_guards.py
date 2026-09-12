"""Guard-hook invocation helpers for the RPC settings handlers."""

from __future__ import annotations

from typing import Any

from airunner_services.api.resource_guards import get_guard

from ._helpers import _is_superuser, _resolve_account_id


def _sanitize_for_resource(
    resource_name: str,
    item: Any | None,
    values: dict[str, Any],
    ws: Any = None,
) -> dict[str, Any]:
    """Run the guard's sanitize hook for *resource_name* (if registered).

    ``item`` is the existing ORM row for updates (may be ``None`` for
    creates).  Returns the (possibly modified) values dict.

    When ``ws`` is provided, ``is_superuser`` is passed to the guard
    hook so it can treat admin and non-admin callers differently.
    """
    guard = get_guard(resource_name)
    if guard is None:
        return values
    is_superuser = _is_superuser(ws) if ws else False
    if item is None:
        return guard.sanitize_create(values, is_superuser=is_superuser)
    return guard.sanitize_update(item, values, is_superuser=is_superuser)


def _check_before_delete(
    resource_name: str, item: Any, ws: Any = None,
) -> None:
    """Call the guard's ``before_delete`` hook if registered.

    When *ws* is provided, ``is_superuser`` is passed to the guard
    hook so it can treat admin and non-admin callers differently —
    mirrors how ``_sanitize_for_resource`` passes the role for
    create/update operations.
    """
    guard = get_guard(resource_name)
    if guard is not None:
        is_superuser = _is_superuser(ws) if ws else False
        guard.before_delete(item, is_superuser=is_superuser)


def _check_before_reset_defaults(resource_name: str, item: Any) -> None:
    """Call the guard's ``before_reset_defaults`` hook if registered."""
    guard = get_guard(resource_name)
    if guard is not None:
        guard.before_reset_defaults(item)


def _check_guard_ownership(
    resource_name: str, item: Any, ws: Any,
) -> None:
    """Call the guard's ``check_ownership`` hook if registered."""
    guard = get_guard(resource_name)
    if guard is None:
        return
    account_id = _resolve_account_id({"ws": ws})
    is_superuser = _is_superuser(ws) if ws else False
    guard.check_ownership(item, account_id, is_superuser)


def _apply_read_filter(
    resource_name: str, record: dict, ws: Any
) -> dict:
    """Run the guard's read-filter hook for *resource_name*, if any."""
    guard = get_guard(resource_name)
    if guard is None:
        return record
    return guard.filter_read(record, _is_superuser(ws))
