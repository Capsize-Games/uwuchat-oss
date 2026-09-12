"""WebSocket RPC handlers for the headlesscode endpoints.

The client's ``request()`` helper (``api/client-base.ts``) sends RPC
messages over the unified ``/api/v1/events`` WebSocket, which the
server dispatches via ``@_rpc_register`` — not the HTTP router.  These
handlers are thin wrappers over :mod:`headlesscode_service`, the same
account-scoped core the HTTP routes use.

Authentication comes from the socket's JWT (``resolve_ws_tenant``),
matching the HTTP path's ``require_auth`` dependency.
"""

from __future__ import annotations

from typing import Any

from airunner_services.api.routes.events import _rpc_register
from airunner_services.api.ws_tenant import resolve_ws_tenant
from projects.uwuchat.server import headlesscode_service as hc
from projects.uwuchat.server.headlesscode_service import HeadlesscodeError

_UNAUTHENTICATED = {"status": 401, "body": {"error": "Authentication required"}}


def _account_id(ws: Any) -> int | None:
    """Return the socket's account id, or None when unauthenticated."""
    _tenant, account_id = resolve_ws_tenant(ws)
    return account_id


def _error(exc: HeadlesscodeError) -> dict[str, Any]:
    """Map a service error onto an RPC response."""
    return {"status": exc.status, "body": {"error": exc.message}}


@_rpc_register("GET", "/api/v1/uwuchat/headlesscode/projects")
async def _rpc_list_projects(
    body: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """RPC handler: list the account's registered projects."""
    del body
    account_id = _account_id(ws)
    if account_id is None:
        return _UNAUTHENTICATED
    try:
        projects = hc.list_projects(account_id)
    except HeadlesscodeError as exc:
        return _error(exc)
    return {"status": 200, "body": {"projects": projects}}


@_rpc_register("POST", "/api/v1/uwuchat/headlesscode/projects")
async def _rpc_create_project(
    body: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """RPC handler: register a new project."""
    account_id = _account_id(ws)
    if account_id is None:
        return _UNAUTHENTICATED
    try:
        project = await hc.create_project(
            account_id,
            str(body.get("name", "")),
            str(body.get("repo_path", "")),
            str(body.get("workspace_root", "")),
        )
    except HeadlesscodeError as exc:
        return _error(exc)
    return {"status": 201, "body": project}


@_rpc_register("PATCH", "/api/v1/uwuchat/headlesscode/projects/{project_id}")
async def _rpc_update_project(
    body: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """RPC handler: update one registered project."""
    account_id = _account_id(ws)
    if account_id is None:
        return _UNAUTHENTICATED
    try:
        project = await hc.update_project(
            account_id,
            int(kw.get("path_params", {}).get("project_id", 0)),
            str(body.get("name", "")),
            str(body.get("repo_path", "")),
            str(body.get("workspace_root", "")),
        )
    except HeadlesscodeError as exc:
        return _error(exc)
    return {"status": 200, "body": project}


@_rpc_register("DELETE", "/api/v1/uwuchat/headlesscode/projects/{project_id}")
async def _rpc_delete_project(
    body: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """RPC handler: soft-delete one registered project."""
    del body
    account_id = _account_id(ws)
    if account_id is None:
        return _UNAUTHENTICATED
    try:
        hc.delete_project(
            account_id,
            int(kw.get("path_params", {}).get("project_id", 0)),
        )
    except HeadlesscodeError as exc:
        return _error(exc)
    return {"status": 204, "body": {}}


@_rpc_register("GET", "/api/v1/uwuchat/headlesscode/sessions/{session_id}")
async def _rpc_get_session_detail(
    body: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """RPC handler: session header plus durable event transcript."""
    del body
    account_id = _account_id(ws)
    if account_id is None:
        return _UNAUTHENTICATED
    detail = hc.get_session_detail(
        account_id,
        str(kw.get("path_params", {}).get("session_id", "")),
    )
    if detail is None:
        return {"status": 404, "body": {"error": "Session not found"}}
    return {"status": 200, "body": detail}


@_rpc_register(
    "POST", "/api/v1/uwuchat/headlesscode/sessions/{session_id}/message",
)
async def _rpc_inject_session_message(
    body: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """RPC handler: forward a mid-session message to the agent."""
    account_id = _account_id(ws)
    if account_id is None:
        return _UNAUTHENTICATED
    session_id = str(kw.get("path_params", {}).get("session_id", ""))
    try:
        await hc.forward_session_message(
            account_id, session_id, str(body.get("text", "")),
        )
    except HeadlesscodeError as exc:
        return _error(exc)
    return {"status": 200, "body": {"ok": True, "session_id": session_id}}
