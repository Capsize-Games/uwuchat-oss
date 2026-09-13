"""Shared helpers for the RPC settings resource-store handlers."""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any

from airunner_services.api.resource_guards import ResourceGuardRejected
from airunner_services.api.routes.events import _rpc_error_response

from ._registry import resource_store_table

logger = logging.getLogger(__name__)

_CHATBOT_TEXT_FIELDS = {"name", "botname", "bot_personality"}

_CHATBOT_RATE_LIMIT = 3
_CHATBOT_RATE_LIMIT_WINDOW_HOURS = 24

_SECRET_FIELD_PATTERN = re.compile(
    r"(api_key|access_token|refresh_token|secret|password|"
    r"private_key|client_secret)",
    re.IGNORECASE,
)


def _record_from_item(item) -> dict:
    """Build a flat dict from one dynamic ORM row.

    Fields that match a credential pattern are always dropped,
    regardless of resource, guard, or caller role — this generic
    browser-facing WS channel must never carry secret material.
    Per-resource guards receive the already-redacted record and
    may narrow further, but can never recover a dropped secret field.
    """
    return {
        c.name: getattr(item, c.name)
        for c in item.__table__.columns
        if not _SECRET_FIELD_PATTERN.search(c.name)
    }


def _apply_filters(query, table, filters: dict):
    """Apply equality filters to a SQLAlchemy query."""
    for key, val in (filters or {}).items():
        col = getattr(table, key, None)
        if col is not None:
            query = query.filter(col == val)
    return query


def _is_superuser(ws: Any) -> bool:
    """Return True when the WS connection belongs to a superuser.

    Queries ``Account`` via ``public_session_scope()`` directly rather
    than ``Account.objects.get()`` — that manager goes through the
    generic, tenant-scoped ``session_scope()``, which resolves its
    session from the *ambient* tenant context. When called from inside
    an already-open tenant write transaction (e.g. from
    ``_sanitize_for_resource`` during a singleton PUT), it would share
    that same session object and its own ``session.expunge_all()``
    would silently detach the row the outer transaction is updating,
    before the caller's ``setattr`` loop ever runs.
    """
    try:
        from airunner_services.api.ws_tenant import resolve_ws_tenant

        _tenant, account_id = resolve_ws_tenant(ws)
        if account_id is None:
            return False
        from airunner_services.database.session import (
            public_session_scope,
        )
        from extensions.auth.server.models import Account

        with public_session_scope() as session:
            acct = (
                session.query(Account)
                .filter(Account.id == account_id)
                .first()
            )
            return bool(acct and getattr(acct, "is_superuser", False))
    except Exception:
        return False


def _settings_auth(kw: dict) -> int | None:
    """Resolve and return the account_id from the WS context.

    Returns None when the socket is unauthenticated — callers must
    reject the request with a 401-equivalent response.
    """
    ws = kw.get("ws")
    if ws is None:
        return None
    from airunner_services.api.ws_tenant import resolve_ws_tenant

    _tenant, account_id = resolve_ws_tenant(ws)
    return account_id


def _resolve_account_id(kw: dict) -> int | None:
    """Extract the authenticated account ID from RPC keyword args."""
    ws = kw.get("ws")
    if ws is None:
        return None
    from airunner_services.api.ws_tenant import resolve_ws_tenant

    _tenant, account_id = resolve_ws_tenant(ws)
    return account_id


def _ws_connection_info(ws) -> str:
    """Return a short diagnostic string for a WebSocket connection."""
    if ws is None:
        return "ws=None"
    try:
        client = getattr(ws, "client", None)
        host = client.host if client and hasattr(client, "host") else "?"
        port = client.port if client and hasattr(client, "port") else "?"
        return f"ws client={host}:{port}"
    except Exception:
        return "ws=<error>"


def _validate_chatbot_values(values: dict) -> dict | None:
    """Run safety validation on Chatbot text fields.

    Returns an error dict on failure, None on success.
    """
    from airunner_services.llm.safety.validators import (
        ValidationError,
        validate_chatbot_field,
    )

    for field, value in values.items():
        if field not in _CHATBOT_TEXT_FIELDS:
            continue
        if not isinstance(value, str):
            continue
        try:
            values[field] = validate_chatbot_field(field, value)
        except ValidationError:
            return {
                "status": 422,
                "body": {"error": "Profile contains disallowed content."},
            }
    return None


def _chatbot_rate_limit_error(ws: Any) -> dict | None:
    """Return a 429 error dict if the chatbot creation rate limit is
    exceeded, else None.

    Superusers are exempt. Shared by the quota pre-check endpoint and
    the actual create endpoint so both enforce the identical limit.
    """
    if _is_superuser(ws):
        return None
    table = resource_store_table("Chatbot")
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(
        hours=_CHATBOT_RATE_LIMIT_WINDOW_HOURS
    )
    with table.objects.transaction() as tx:
        recent_count = tx.query(table).filter(
            table.created_at >= cutoff,
            table.deleted.is_(False),
        ).count()
    if recent_count < _CHATBOT_RATE_LIMIT:
        return None
    return {
        "status": 429,
        "body": {
            "error_code": "rate_limit_exceeded",
            "error": (
                "Rate limit exceeded. "
                f"Maximum {_CHATBOT_RATE_LIMIT} new chatbots per "
                f"{_CHATBOT_RATE_LIMIT_WINDOW_HOURS} hours."
            ),
        },
    }


def _reset_column_defaults(table, item) -> None:
    """Reset columns that have static (non-callable) defaults."""
    from sqlalchemy.sql.schema import ColumnDefault

    for c in table.__table__.columns:
        col_name = c.name
        if col_name in ("id",) or col_name.startswith("_"):
            continue
        if c.default is not None and isinstance(c.default, ColumnDefault):
            val = c.default.arg
            if not callable(val):
                setattr(item, col_name, val)


def _guard_error_response(exc: Exception) -> dict[str, Any]:
    """Map a guard rejection or unexpected handler error to an RPC
    response."""
    if isinstance(exc, ResourceGuardRejected):
        return {"status": 403, "body": {"error": exc.message}}
    return _rpc_error_response(exc, logger=logger, context="error")
