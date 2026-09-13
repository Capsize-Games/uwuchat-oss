"""WS-RPC handlers for the host-executor policy (UwUchat code mode).

Reached over the unified ``/api/v1/events`` WebSocket via the client's
``request()`` helper — same convention as ``random_chatbot_rpc.py``.

Endpoints:
- ``GET  /api/v1/uwuchat/host-exec/policy``  read the caller's policy
- ``POST /api/v1/uwuchat/host-exec/policy``  save the caller's policy
- ``POST /api/v1/uwuchat/host-exec/classify``  classify a command as
  container vs host (used by the client to decide whether a command
  needs the consent flow)

The actual command execution happens in the host-executor agent
(``scripts/host-executor.py``); this module owns the persisted policy
that gates it.  See plans/uwuchat-host-executor-with-consent.md.
"""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events import (
    _rpc_error_response,
    _rpc_register,
)
from airunner_services.api.ws_tenant import resolve_ws_tenant
from airunner_services.database.models.user import User

from projects.uwuchat.server.host_exec_policy import (
    HostExecPolicy,
    classify_group,
    needs_host,
)

logger = logging.getLogger(__name__)


def _user(ws: Any) -> User | None:
    """Return the caller's User row, or None when unauthenticated."""
    _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return None
    return User.objects.get(account_id)


def _unauthorized() -> dict[str, Any]:
    """Return the standard 401 RPC body."""
    return {"status": 401, "body": {"error": "Authentication required"}}


@_rpc_register("GET", "/api/v1/uwuchat/host-exec/policy")
async def _rpc_get_host_exec_policy(
    body: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """Return the caller's host-executor policy."""
    del body, kw
    user = _user(ws)
    if user is None:
        return _unauthorized()
    try:
        policy = HostExecPolicy.from_user_data(user)
        return {"status": 200, "body": {"policy": policy.__dict__}}
    except Exception as exc:
        return _rpc_error_response(
            exc, logger=logger, context="host-exec get-policy error",
        )


@_rpc_register("POST", "/api/v1/uwuchat/host-exec/policy")
async def _rpc_set_host_exec_policy(
    body: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """Persist the caller's host-executor policy."""
    del kw
    user = _user(ws)
    if user is None:
        return _unauthorized()
    raw = body.get("policy") or {}
    try:
        policy = HostExecPolicy()
        if isinstance(raw.get("enabled"), bool):
            policy.enabled = raw["enabled"]
        if isinstance(raw.get("enable_all"), bool):
            policy.enable_all = raw["enable_all"]
        if isinstance(raw.get("groups"), dict):
            for key, value in raw["groups"].items():
                if key in policy.groups and isinstance(value, bool):
                    policy.groups[key] = value
        for key in ("whitelist", "blacklist", "allow_always"):
            if isinstance(raw.get(key), list):
                setattr(
                    policy, key,
                    [str(x) for x in raw[key] if str(x).strip()],
                )
        HostExecPolicy.save_to_user(user, policy)
        return {"status": 200, "body": {"policy": policy.__dict__}}
    except Exception as exc:
        return _rpc_error_response(
            exc, logger=logger, context="host-exec set-policy error",
        )


@_rpc_register("POST", "/api/v1/uwuchat/host-exec/classify")
async def _rpc_classify_command(
    body: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """Classify one command as container-safe vs needs-host."""
    del ws, kw
    command = str(body.get("command") or "").strip()
    if not command:
        return {"status": 400, "body": {"error": "command is required"}}
    return {
        "status": 200,
        "body": {
            "command": command,
            "group": classify_group(command),
            "needs_host": needs_host(command),
        },
    }


@_rpc_register("POST", "/api/v1/uwuchat/host-exec/consent")
async def _rpc_host_exec_consent(
    body: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """Record the user's approve/deny/always choice for a host command.

    The choice is applied to the caller's policy (``always`` adds to
    allow_always) and echoed back.  Actual execution happens in the
    host-executor agent; this endpoint is the durable consent record
    and the client-facing confirmation.
    """
    del kw
    user = _user(ws)
    if user is None:
        return _unauthorized()
    req_id = str(body.get("id") or "")
    command = str(body.get("command") or "").strip()
    choice = str(body.get("consent") or "").lower()
    if not req_id or not command:
        return {"status": 400, "body": {"error": "id and command are required"}}
    if choice not in ("approve", "deny", "always"):
        return {"status": 400, "body": {"error": "consent must be approve|deny|always"}}
    try:
        policy = HostExecPolicy.from_user_data(user)
        if choice == "always" and command not in policy.allow_always:
            policy.allow_always = list(policy.allow_always) + [command]
            HostExecPolicy.save_to_user(user, policy)
        return {
            "status": 200,
            "body": {
                "id": req_id,
                "command": command,
                "consent": choice,
                "allowed": choice != "deny",
            },
        }
    except Exception as exc:
        return _rpc_error_response(
            exc, logger=logger, context="host-exec consent error",
        )


__all__ = [
    "_rpc_classify_command",
    "_rpc_get_host_exec_policy",
    "_rpc_host_exec_consent",
    "_rpc_set_host_exec_policy",
]
