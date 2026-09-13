"""Client for the host-executor agent (scripts/host-executor.py).

The server talks to the host agent over a local unix socket with a
token, sending ``execute`` / ``consent`` JSON requests and reading the
JSON response.  The agent path/token come from settings
(``HEADLESSCODE_HOST_EXEC_SOCKET`` / ``HEADLESSCODE_HOST_EXEC_TOKEN``)
so the same server can be pointed at any host agent instance.

See plans/uwuchat-host-executor-with-consent.md.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from typing import Any

from airunner_services.conf import settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 60.0


def _socket_path() -> str:
    """Return the host-executor unix socket path.

    Defaults to a path under the repo's server dir (bind-mounted into the
    server container at /app/server), so both the host agent and the
    containerized server can reach the same socket.  Override via
    HEADLESSCODE_HOST_EXEC_SOCKET (host side) / settings.
    """
    return os.environ.get(
        "HEADLESSCODE_HOST_EXEC_SOCKET",
        str(settings.get("HEADLESSCODE_HOST_EXEC_SOCKET", "") or "")
        or "/app/server/.host-exec.sock",
    )


def _token() -> str:
    """Return the host-executor auth token."""
    return os.environ.get(
        "HEADLESSCODE_HOST_EXEC_TOKEN",
        str(settings.get("HEADLESSCODE_HOST_EXEC_TOKEN", "") or ""),
    )


def _send(payload: dict[str, Any]) -> dict[str, Any]:
    """Send one JSON request to the host agent and read the response."""
    payload = dict(payload)
    payload["token"] = _token()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(_TIMEOUT_SECONDS)
        conn.connect(_socket_path())
        conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        data = conn.recv(65536)
    if not data:
        return {"status": "error", "output": "no response from host executor"}
    try:
        return json.loads(data.decode("utf-8"))
    except ValueError:
        return {"status": "error", "output": "invalid response from host executor"}


def execute(
    command: str, cwd: str | None = None, timeout: int = 120,
) -> dict[str, Any]:
    """Request host execution of *command*.

    Returns the agent's response: ``status`` in
    ``ok|denied|needs_consent|error`` plus ``output``.
    """
    return _send({
        "type": "execute",
        "id": _req_id(command),
        "cmd": command,
        "cwd": cwd,
        "timeout": timeout,
    })


def consent(
    req_id: str, choice: str,
) -> dict[str, Any]:
    """Send a consent choice (approve/deny/always) for a pending request."""
    return _send({
        "type": "consent",
        "id": req_id,
        "consent": choice,
    })


def _req_id(command: str) -> str:
    """Return a stable request id derived from the command."""
    import hashlib

    return hashlib.sha1(command.encode("utf-8")).hexdigest()[:16]


def available() -> bool:
    """Return True when the host agent socket is reachable."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(2.0)
            conn.connect(_socket_path())
        return True
    except OSError:
        return False


__all__ = ["available", "consent", "execute"]
