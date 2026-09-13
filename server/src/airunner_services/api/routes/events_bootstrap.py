"""Session-bootstrap payload builders for the unified WebSocket.

One small helper per resource so that each function stays under the
20-line limit.  Called by :func:`_build_bootstrap_payload` which
assembles the full payload with per-field failure tolerance.

Reuses the existing guard-filtering helpers from
:mod:`airunner_services.api.routes.rpc_settings` — the bootstrap
message carries exactly the same fields the singleton / query RPC
handlers would return.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


async def _bootstrap_application_settings(
    websocket: WebSocket,
) -> dict[str, Any]:
    """Return the filtered ``ApplicationSettings`` singleton record."""
    from airunner_services.api.routes.rpc_settings import (
        _apply_read_filter,
        _record_from_item,
        resource_store_table,
    )

    table = resource_store_table("ApplicationSettings")
    with table.objects.transaction() as tx:
        item = tx.query(table).first()
        if item is None:
            item = table()
            tx.add(item)
        record = _record_from_item(item)
        return _apply_read_filter(
            "ApplicationSettings", record, websocket
        )


async def _bootstrap_language_settings(
    websocket: WebSocket,
) -> dict[str, Any]:
    """Return the filtered ``LanguageSettings`` singleton record."""
    from airunner_services.api.routes.rpc_settings import (
        _apply_read_filter,
        _record_from_item,
        resource_store_table,
    )

    table = resource_store_table("LanguageSettings")
    with table.objects.transaction() as tx:
        item = tx.query(table).first()
        if item is None:
            item = table()
            tx.add(item)
        record = _record_from_item(item)
        return _apply_read_filter(
            "LanguageSettings", record, websocket
        )


async def _bootstrap_chatbots(
    websocket: WebSocket,
) -> list[dict[str, Any]]:
    """Return the filtered ``Chatbot`` roster (active, not deleted)."""
    from airunner_services.api.routes.rpc_settings import (
        _apply_filters,
        _apply_read_filter,
        _record_from_item,
        resource_store_table,
    )

    table = resource_store_table("Chatbot")
    with table.objects.transaction() as tx:
        query = tx.query(table)
        query = _apply_filters(query, table, {"deleted": False})
        items = query.all()
        return [
            _apply_read_filter(
                "Chatbot", _record_from_item(item), websocket
            )
            for item in items
        ]


async def _bootstrap_project_setting(
    websocket: WebSocket,
) -> dict[str, Any]:
    """Return the ``ProjectSetting`` row for key ``immersion``."""
    from airunner_services.api.routes.rpc_settings import (
        _apply_filters,
        _apply_read_filter,
        _record_from_item,
        resource_store_table,
    )

    table = resource_store_table("ProjectSetting")
    with table.objects.transaction() as tx:
        query = tx.query(table)
        query = _apply_filters(query, table, {"key": "immersion"})
        item = query.first()
        record = (
            _record_from_item(item)
            if item is not None
            else {"key": "immersion", "value": "full"}
        )
        return _apply_read_filter(
            "ProjectSetting", record, websocket
        )


async def build_bootstrap_payload(
    account_id: int | None, websocket: WebSocket
) -> dict[str, Any]:
    """Build the full session-bootstrap payload.

    Each resource is fetched independently — one failure does not
    prevent the others from being returned.  The caller is responsible
    for activating the tenant and DEK scopes before invoking this.
    """
    from airunner_services.api.ws_tenant import ws_dek_scope

    body: dict[str, Any] = {}

    with ws_dek_scope(account_id):
        # ── ApplicationSettings ──
        try:
            body["application_settings"] = (
                await _bootstrap_application_settings(websocket)
            )
        except Exception as exc:
            logger.warning(
                "bootstrap: ApplicationSettings failed: %s",
                exc,
                exc_info=True,
            )
            body["application_settings"] = {}

        # ── LanguageSettings ──
        try:
            body["language_settings"] = (
                await _bootstrap_language_settings(websocket)
            )
        except Exception as exc:
            logger.warning(
                "bootstrap: LanguageSettings failed: %s",
                exc,
                exc_info=True,
            )
            body["language_settings"] = {}

        # ── Chatbot roster ──
        try:
            body["chatbots"] = await _bootstrap_chatbots(websocket)
        except Exception as exc:
            logger.warning(
                "bootstrap: Chatbot roster failed: %s",
                exc,
                exc_info=True,
            )
            body["chatbots"] = []

        # ── ProjectSetting (immersion) ──
        try:
            record = await _bootstrap_project_setting(websocket)
            body["project_setting"] = {"immersion": record}
        except Exception as exc:
            logger.warning(
                "bootstrap: ProjectSetting failed: %s",
                exc,
                exc_info=True,
            )
            body["project_setting"] = {
                "immersion": {"key": "immersion", "value": "full"}
            }

    return body
