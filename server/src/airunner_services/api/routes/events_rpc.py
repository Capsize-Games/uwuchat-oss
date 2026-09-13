"""RPC dispatch system for the unified WebSocket endpoint."""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from fastapi import WebSocket

from airunner_services.utils.error_sanitizer import (
    log_and_sanitize,
    sanitize_exception_code,
)

# ── Supported event types ────────────────────────────────────────────────

EVENT_IMAGES = "images"
EVENT_LORAS = "loras"
EVENT_EMBEDDINGS = "embeddings"
EVENT_DOCUMENTS = "documents"
EVENT_MODEL_STATUS = "model_status"
EVENT_INDEX_PROGRESS = "index_progress"
EVENT_DOWNLOADS = "downloads"
EVENT_CIVITAI_THUMBNAIL = "civitai_thumbnail"
EVENT_HARDWARE = "hardware"
EVENT_PROACTIVE_MESSAGE = "proactive_message"
EVENT_ROOM_MESSAGE = "room_message"
EVENT_WEATHER_DATA = "weather_data"
EVENT_GEMS_BALANCE = "gems_balance"
EVENT_HEADLESSCODE_SESSION = "headlesscode_session"
EVENT_HEADLESSCODE_PROJECTS = "headlesscode_projects"
EVENT_UWU_CREATION = "uwu_creation"

ALL_EVENTS = frozenset(
    {
        EVENT_IMAGES,
        EVENT_LORAS,
        EVENT_EMBEDDINGS,
        EVENT_DOCUMENTS,
        EVENT_MODEL_STATUS,
        EVENT_INDEX_PROGRESS,
        EVENT_DOWNLOADS,
        EVENT_CIVITAI_THUMBNAIL,
        EVENT_HARDWARE,
        EVENT_PROACTIVE_MESSAGE,
        EVENT_ROOM_MESSAGE,
        EVENT_WEATHER_DATA,
        EVENT_GEMS_BALANCE,
        EVENT_HEADLESSCODE_SESSION,
        EVENT_HEADLESSCODE_PROJECTS,
        EVENT_UWU_CREATION,
    }
)

# Event types that carry user-specific content and must be scoped to
# the owning account.  WsEventBus.broadcast() checks
# ``subscriber.account_id`` against the broadcast ``account_id`` for
# these types.  Unauthenticated subscribers MUST NOT be able to
# subscribe to them (enforced in _handle_subscribe in events.py).
_ACCOUNT_SCOPED_EVENTS: frozenset[str] = frozenset({
    EVENT_PROACTIVE_MESSAGE,
    EVENT_GEMS_BALANCE,
    EVENT_WEATHER_DATA,
    EVENT_ROOM_MESSAGE,
    EVENT_HEADLESSCODE_SESSION,
    EVENT_HEADLESSCODE_PROJECTS,
    EVENT_UWU_CREATION,
})

# ── RPC error helper ─────────────────────────────────────────────────────


def _rpc_error_response(
    exc: Exception,
    *,
    logger: logging.Logger,
    context: str,
) -> dict[str, Any]:
    """Log the full exception server-side; return a sanitized
    RPC error body for the client.

    Mirrors ``server_middleware.global_exception_handler`` for the
    HTTP path, since ``@app.exception_handler`` never fires for
    WebSocket routes.

    Gated on ``AIRUNNER_DEBUG`` only (no loopback check — there is
    no ``Request`` object in the WS path).
    """
    message = log_and_sanitize(exc, logger=logger, context=context)
    body: dict[str, Any] = {"error": "Internal server error"}
    if message != "Internal server error":
        body["detail"] = message
    code = sanitize_exception_code(exc)
    if code is not None:
        body["error_code"] = code
    return {"status": 500, "body": body}


# ── RPC dispatcher ───────────────────────────────────────────────────────

_rpc_routes: list[tuple[str, re.Pattern, list[str], Callable]] = []
_rpc_lock = threading.Lock()


def _path_to_regex(pattern: str) -> tuple[re.Pattern, list[str]]:
    """Convert a path pattern like ``/resources/{name}/singleton``
    to a compiled regex and list of parameter names."""
    param_names: list[str] = []
    parts: list[str] = []
    for segment in pattern.split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            name = segment[1:-1]
            param_names.append(name)
            parts.append(r"([^/]+)")
        else:
            parts.append(re.escape(segment))
    regex_str = "^" + "/".join(parts) + "$"
    return re.compile(regex_str), param_names


def _rpc_register(
    method: str,
    path: str,
) -> Callable:
    """Decorator that registers a handler for a (method, path) pair."""
    pattern, param_names = _path_to_regex(path)

    def decorator(func: Callable) -> Callable:
        with _rpc_lock:
            _rpc_routes.append((method.upper(), pattern, param_names, func))
        return func

    return decorator


async def _dispatch_rpc(
    method: str,
    path: str,
    body: dict[str, Any] | None,
    websocket: WebSocket,
) -> dict[str, Any]:
    """Dispatch an RPC message to the registered handler."""
    split = urlsplit(path)
    clean_path = split.path
    # Merge query-string params into the body so handlers can read params
    # the client passes in the URL (e.g. ?conversation_id=11). The client
    # sends these in the query string with an empty body, so without this
    # merge the handler would never see them. Body values take precedence.
    merged_body: dict[str, Any] = dict(body or {})
    if split.query:
        for key, values in parse_qs(split.query).items():
            if key not in merged_body:
                merged_body[key] = values[0] if len(values) == 1 else values
    handler_entry, path_params = _find_rpc_handler(method.upper(), clean_path)
    if handler_entry is None:
        return {
            "status": 404,
            "body": {"error": f"Not found: {method} {path}"},
        }
    try:
        kw: dict[str, Any] = {"body": merged_body, "ws": websocket}
        if path_params:
            kw["path_params"] = path_params
        result = await handler_entry(**kw)
        return result
    except Exception as exc:
        return _rpc_error_response(
            exc,
            logger=logging.getLogger(__name__),
            context=f"RPC handler error: {method} {path}",
        )


def _find_rpc_handler(
    method_upper: str,
    clean_path: str,
) -> tuple[Callable | None, dict[str, str]]:
    """Find the matching RPC handler for a method and path.

    When several registered patterns match (e.g. the singleton route
    ``PUT /resources/{name}/singleton`` and the generic CRUD route
    ``PUT /resources/{name}/{resource_id}`` both match
    ``/resources/User/singleton``), the **most specific** pattern wins:
    the one with the fewest ``{param}`` segments.  Registration order is
    only a tiebreaker — this keeps literal suffix routes (``/singleton``,
    ``/first``, ``/query``, ``/quota``) from being shadowed by a later
    ``{resource_id}`` pattern.
    """
    with _rpc_lock:
        best: tuple[Callable | None, dict[str, str], int] | None = None
        for rpc_method, pattern, param_names, func in _rpc_routes:
            if rpc_method != method_upper:
                continue
            match = pattern.match(clean_path)
            if not match:
                continue
            specificity = -len(param_names)
            if best is None or specificity > best[2]:
                best = (
                    func,
                    dict(zip(param_names, match.groups())),
                    specificity,
                )
        if best is not None:
            return best[0], best[1]
    return None, {}


@_rpc_register("GET", "/health")
@_rpc_register("GET", "/api/v1/health")
async def _rpc_health(body: dict, **kwargs: Any) -> dict[str, Any]:
    """Return server health status."""
    return {
        "status": 200,
        "body": {"status": "healthy", "service": "airunner"},
    }
