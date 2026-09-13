"""Auth-guarded CRUD RPC handlers for the settings resource store."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from airunner_services.api.routes.events import _rpc_register

from ._guards import (
    _apply_read_filter,
    _check_before_delete,
    _check_before_reset_defaults,
    _check_guard_ownership,
    _sanitize_for_resource,
)
from ._helpers import (
    _apply_filters,
    _guard_error_response,
    _record_from_item,
    _reset_column_defaults,
    _validate_chatbot_values,
)
from ._registry import resource_store_table

logger = logging.getLogger(__name__)

# ``_settings_auth`` is resolved through the package module at call time
# so tests that patch ``rpc_settings._settings_auth`` (on either import
# tree) are honored — a submodule-global binding would bypass the patch.
_pkg = importlib.import_module(__package__)


@_rpc_register("PUT", "/api/v1/settings/resources/{name}/{resource_id}")
async def _rpc_settings_update_by_id(body: dict, **kw: Any) -> dict[str, Any]:
    """Update a resource by ID."""
    if _pkg._settings_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    resource_name = pp.get("name", "")
    raw_id = pp.get("resource_id", "")
    if not raw_id.isdigit():
        return {"status": 400, "body": {"error": "Invalid ID"}}
    values: dict = body.get("values", {})
    if resource_name == "Chatbot":
        err = _validate_chatbot_values(values)
        if err:
            return err
    try:
        table = resource_store_table(resource_name)
        with table.objects.transaction() as tx:
            item = tx.query(table).get(int(raw_id))
            if item is None:
                return {"status": 404, "body": {"error": "Not found"}}
            _check_guard_ownership(resource_name, item, kw.get("ws"))
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


@_rpc_register("DELETE", "/api/v1/settings/resources/{name}/{resource_id}")
async def _rpc_settings_delete(body: dict, **kw: Any) -> dict[str, Any]:
    """Delete a resource by ID."""
    if _pkg._settings_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    resource_name = pp.get("name", "")
    raw_id = pp.get("resource_id", "")
    if not raw_id.isdigit():
        return {"status": 400, "body": {"error": "Invalid ID"}}
    try:
        table = resource_store_table(resource_name)
        with table.objects.transaction() as tx:
            item = tx.query(table).get(int(raw_id))
            if item is None:
                return {"status": 404, "body": {"error": "Not found"}}
            _check_guard_ownership(resource_name, item, kw.get("ws"))
            _check_before_delete(
                resource_name, item, ws=kw.get("ws"),
            )
            tx.delete(item)
        return {"status": 200, "body": {"deleted": True}}
    except Exception as exc:
        return _guard_error_response(exc)


@_rpc_register(
    "POST", "/api/v1/settings/resources/{name}/{resource_id}/reset-defaults"
)
async def _rpc_settings_reset_defaults(
    body: dict, **kw: Any
) -> dict[str, Any]:
    """Reset a resource to its column defaults."""
    if _pkg._settings_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    resource_name = pp.get("name", "")
    raw_id = pp.get("resource_id", "")
    if not raw_id.isdigit():
        return {"status": 400, "body": {"error": "Invalid ID"}}
    try:
        table = resource_store_table(resource_name)
        with table.objects.transaction() as tx:
            item = tx.query(table).get(int(raw_id))
            if item is None:
                return {"status": 404, "body": {"error": "Not found"}}
            _check_guard_ownership(resource_name, item, kw.get("ws"))
            _check_before_reset_defaults(resource_name, item)
            _reset_column_defaults(table, item)
            record = _record_from_item(item)
        ws = kw.get("ws")
        record = _apply_read_filter(resource_name, record, ws)
        return {"status": 200, "body": record}
    except Exception as exc:
        return _guard_error_response(exc)


@_rpc_register(
    "POST", "/api/v1/settings/resources/{name}/{resource_id}/make-current"
)
async def _rpc_settings_make_current(body: dict, **kw: Any) -> dict[str, Any]:
    """Set one record as 'current', clearing the flag on all others.

    Works for any resource that has a boolean 'current' column (e.g. Chatbot).
    """
    if _pkg._settings_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    resource_name = pp.get("name", "")
    raw_id = pp.get("resource_id", "")
    if not raw_id.isdigit():
        return {"status": 400, "body": {"error": "Invalid ID"}}
    target_id = int(raw_id)
    try:
        table = resource_store_table(resource_name)
        with table.objects.transaction() as tx:
            # Clear all
            for row in tx.query(table).all():
                if hasattr(row, "current"):
                    row.current = False
            # Set target
            item = tx.query(table).get(target_id)
            if item is None:
                return {"status": 404, "body": {"error": "Not found"}}
            _check_guard_ownership(resource_name, item, kw.get("ws"))
            item.current = True
            record = _record_from_item(item)
        ws = kw.get("ws")
        record = _apply_read_filter(resource_name, record, ws)
        return {"status": 200, "body": {"record": record}}
    except Exception as exc:
        return _guard_error_response(exc)


@_rpc_register("POST", "/api/v1/settings/resources/{name}/query")
async def _rpc_settings_query(body: dict, **kw: Any) -> dict[str, Any]:
    """Query resources with optional equality filters."""
    if _pkg._settings_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    resource_name = pp.get("name", "")
    filters: dict = body.get("filters", {})
    try:
        table = resource_store_table(resource_name)
        with table.objects.transaction() as tx:
            query = tx.query(table)
            query = _apply_filters(query, table, filters)
            items = query.all()
            records = [
                _apply_read_filter(
                    resource_name, _record_from_item(item), kw.get("ws")
                )
                for item in items
            ]
        return {"status": 200, "body": {"records": records}}
    except Exception as exc:
        logger.warning(
            "Resource query failed for %s (filters=%r): %s",
            resource_name,
            filters,
            exc,
            exc_info=True,
        )
        return {"status": 200, "body": {"records": []}}


@_rpc_register("POST", "/api/v1/settings/resources/{name}/first")
async def _rpc_settings_first(body: dict, **kw: Any) -> dict[str, Any]:
    """Query first resource matching optional equality filters.

    Accepts an optional ``order_by`` column name in the body — when
    given, results are sorted descending by that column before taking
    the first row (e.g. "give me the most recent Conversation").
    """
    if _pkg._settings_auth(kw) is None:
        return {"status": 401, "body": {"error": "Authentication required"}}
    pp: dict = kw.get("path_params", {})
    resource_name = pp.get("name", "")
    filters: dict = body.get("filters", {})
    order_by = body.get("order_by")
    try:
        table = resource_store_table(resource_name)
        with table.objects.transaction() as tx:
            query = tx.query(table)
            query = _apply_filters(query, table, filters)
            if order_by:
                col = getattr(table, order_by, None)
                if col is not None:
                    query = query.order_by(col.desc())
            item = query.first()
            record = _record_from_item(item) if item else {}
        if record:
            ws = kw.get("ws")
            record = _apply_read_filter(resource_name, record, ws)
        return {"status": 200, "body": {"record": record}}
    except Exception:
        return {"status": 200, "body": {"record": {}}}
