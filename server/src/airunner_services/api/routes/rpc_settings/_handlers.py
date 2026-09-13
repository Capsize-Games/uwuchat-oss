"""Singleton and create/quota RPC handlers for the resource store."""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events import _rpc_register

from ._guards import (
    _apply_read_filter,
    _sanitize_for_resource,
)
from ._helpers import (
    _chatbot_rate_limit_error,
    _guard_error_response,
    _record_from_item,
    _resolve_account_id,
    _validate_chatbot_values,
    _ws_connection_info,
)
from ._registry import resource_store_table

logger = logging.getLogger(__name__)


def _singleton_item(tx, table, resource_name: str, kw: dict, verb: str):
    """Fetch (or create) the singleton row, scoping ``User`` by account.

    Returns ``(item, None)`` on success or ``(None, error_dict)`` when
    the connection is unauthenticated.
    """
    if resource_name != "User":
        item = tx.query(table).first()
        if item is None:
            item = table()
            tx.add(item)
        return item, None
    account_id = _resolve_account_id(kw)
    if account_id is None:
        ws_info = _ws_connection_info(kw.get("ws"))
        logger.warning(
            "User singleton %s rejected — unauthenticated "
            "WS connection: %s",
            verb,
            ws_info,
        )
        return None, {
            "status": 401,
            "body": {"error": "Authentication required"},
        }
    item = tx.query(table).filter(
        table.id == account_id,
    ).first()
    if item is None:
        item = table(id=account_id)
        tx.add(item)
    return item, None


@_rpc_register("GET", "/api/v1/settings/resources/{name}/singleton")
async def _rpc_settings_singleton(body: dict, **kw: Any) -> dict[str, Any]:
    """Get or create a singleton resource.

    For the ``User`` resource, the query is scoped to the authenticated
    account ID so that stale records from a previously-deleted account
    sharing the same tenant schema are never returned.
    """
    pp: dict = kw.get("path_params", {})
    resource_name = pp.get("name", "")
    try:
        table = resource_store_table(resource_name)
        with table.objects.transaction() as tx:
            item, err = _singleton_item(
                tx, table, resource_name, kw, "GET"
            )
            if err:
                return err
            record = _record_from_item(item)
            ws = kw.get("ws")
            record = _apply_read_filter(resource_name, record, ws)
            return {"status": 200, "body": {"record": record}}
    except Exception as exc:
        logger.warning(
            "singleton GET failed for %s: %s", resource_name, exc,
            exc_info=True,
        )
        return {"status": 200, "body": {"record": {}}}


@_rpc_register("PUT", "/api/v1/settings/resources/{name}/singleton")
async def _rpc_settings_singleton_update(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Update a singleton resource.

    For the ``User`` resource, the query is scoped to the authenticated
    account ID so that a stale record from a previously-deleted account
    is never mutated.
    """
    pp: dict = kw.get("path_params", {})
    resource_name = pp.get("name", "")
    values: dict = body.get("values", {})
    try:
        table = resource_store_table(resource_name)
        with table.objects.transaction() as tx:
            item, err = _singleton_item(
                tx, table, resource_name, kw, "PUT"
            )
            if err:
                return err
            values = _sanitize_for_resource(
                resource_name, item, values, ws=kw.get("ws")
            )
            for key, val in values.items():
                if hasattr(item, key):
                    setattr(item, key, val)
            record = _record_from_item(item)
            ws = kw.get("ws")
            record = _apply_read_filter(resource_name, record, ws)
            return {"status": 200, "body": record}
    except Exception as exc:
        return _guard_error_response(exc)


@_rpc_register("POST", "/api/v1/settings/resources/{name}")
async def _rpc_settings_create(body: dict, **kw: Any) -> dict[str, Any]:
    """Create a new resource record."""
    pp: dict = kw.get("path_params", {})
    resource_name = pp.get("name", "")
    values: dict = body.get("values", {})
    try:
        table = resource_store_table(resource_name)
        if resource_name == "Chatbot":
            err = _validate_chatbot_values(values)
            if err:
                return err
            err = _chatbot_rate_limit_error(kw.get("ws"))
            if err:
                return err
        values = _sanitize_for_resource(
            resource_name, None, values, ws=kw.get("ws")
        )
        item = table()
        for key, val in values.items():
            if hasattr(item, key):
                setattr(item, key, val)
        with table.objects.transaction() as tx:
            tx.add(item)
            tx.flush()
            record = _record_from_item(item)
        ws = kw.get("ws")
        record = _apply_read_filter(resource_name, record, ws)
        return {"status": 200, "body": {"record": record}}
    except Exception as exc:
        return _guard_error_response(exc)


@_rpc_register("GET", "/api/v1/settings/resources/{name}/quota")
async def _rpc_settings_quota(body: dict, **kw: Any) -> dict[str, Any]:
    """Check resource creation quota without creating anything.

    Lets the client fail fast on a rate limit before doing expensive
    work (e.g. LLM calls) that would otherwise be wasted on a request
    that was always going to be rejected at creation time.
    """
    pp: dict = kw.get("path_params", {})
    resource_name = pp.get("name", "")
    if resource_name == "Chatbot":
        err = _chatbot_rate_limit_error(kw.get("ws"))
        if err:
            return err
    return {"status": 200, "body": {"ok": True}}
