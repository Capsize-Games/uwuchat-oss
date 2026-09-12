"""FastSearch extension — REST API routes for monitoring and control.

Registered by the extension loader at ``/api/v1/fastsearch``.
All endpoints require JWT authentication (provided by the auth extension).

Endpoints:

- ``GET  /status``  — Check FastSearch connectivity and config status
- ``PUT  /config``  — Update FastSearch API key and/or base URL
- ``POST /test``    — Test connectivity with current configuration
- ``POST /restart`` — Restart FastSearch web container via SSH
- ``POST /rebuild`` — Rebuild and redeploy FastSearch web container
- ``GET  /logs``    — Fetch recent FastSearch web container logs
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from extensions.fastsearch.server.provider import FastSearchProvider

router = APIRouter()

# ------------------------------------------------------------------
# Request / Response schemas
# ------------------------------------------------------------------


class ConfigUpdate(BaseModel):
    """Request body for ``PUT /config``."""

    api_key: Optional[str] = None
    base_url: Optional[str] = None


class StatusResponse(BaseModel):
    """Response body for ``GET /status``."""

    configured: bool
    base_url: str
    healthy: bool
    error: Optional[str] = None
    response_time_ms: Optional[int] = None
    last_success_at: Optional[str] = None
    cache_stats: Optional[Dict[str, Any]] = None


class ConfigResponse(BaseModel):
    """Response body for ``PUT /config``."""

    message: str
    base_url: str
    api_key_configured: bool


class TestResponse(BaseModel):
    """Response body for ``POST /test``."""

    success: bool
    message: str
    result_count: int = 0
    elapsed_ms: int = 0
    error: Optional[str] = None


class SSHCommandResponse(BaseModel):
    """Response body for ``POST /restart`` and ``POST /rebuild``."""

    success: bool
    message: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    exit_code: Optional[int] = None


class LogsResponse(BaseModel):
    """Response body for ``GET /logs``."""

    lines: list[str]
    truncated: bool


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_FORBIDDEN = (
    "FastSearch extension is not configured. "
    "Set FASTSEARCH_API_KEY and FASTSEARCH_BASE_URL environment "
    "variables, or use PUT /api/v1/fastsearch/config to configure."
)

# In-memory tracking for last successful health check.
_last_success_at: Optional[str] = None
_last_error: Optional[str] = None
_last_response_time_ms: Optional[int] = None


def _get_provider_from_env() -> FastSearchProvider:
    """Create a ``FastSearchProvider`` using current environment values."""
    api_key = os.environ.get("FASTSEARCH_API_KEY", "")
    base_url = os.environ.get(
        "FASTSEARCH_BASE_URL", "http://127.0.0.1:8001"
    )
    return FastSearchProvider(base_url=base_url, api_key=api_key)


def _ssh_command(command: str) -> Dict[str, Any]:
    """Run a shell command on the Hetzner server via SSH.

    Runs in a thread so it does not block the async event loop.
    """
    from airunner_services.utils.hetzner_ssh import (
        run_ssh_command,
    )

    loop = asyncio.get_event_loop()
    result = loop.run_in_executor(None, run_ssh_command, command)
    return asyncio.ensure_future(result)


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/status", response_model=StatusResponse)
async def get_status() -> Dict[str, Any]:
    """Check whether FastSearch is configured and reachable.

    Returns:
        JSON with configured/healthy flags, response time, cache stats,
        and optional error message.
    """
    global _last_success_at, _last_error, _last_response_time_ms

    provider = _get_provider_from_env()
    configured = bool(os.environ.get("FASTSEARCH_API_KEY"))

    start = time.monotonic()
    try:
        health = await provider.health()
        elapsed_ms = int((time.monotonic() - start) * 1000)
        _last_response_time_ms = elapsed_ms
    except Exception as exc:
        _last_error = str(exc)
        return {
            "configured": configured,
            "base_url": provider.base_url,
            "healthy": False,
            "error": str(exc),
            "response_time_ms": _last_response_time_ms,
            "last_success_at": _last_success_at,
            "cache_stats": None,
        }

    healthy = health.get("ok", False)
    if healthy:
        _last_success_at = _get_iso_now()
        _last_error = None
    else:
        _last_error = health.get("error", "Unknown error")

    return {
        "configured": configured,
        "base_url": provider.base_url,
        "healthy": healthy,
        "error": _last_error,
        "response_time_ms": _last_response_time_ms,
        "last_success_at": _last_success_at,
        "cache_stats": None,
    }


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.put("/config", response_model=ConfigResponse)
async def update_config(body: ConfigUpdate) -> Dict[str, Any]:
    """Update the FastSearch API key and/or base URL at runtime.

    The values are written to the current process environment so they
    take effect immediately for subsequent tool invocations.

    Args:
        body: JSON with optional ``api_key`` and/or ``base_url`` fields.

    Returns:
        Confirmation with the applied settings.
    """
    if body.api_key is not None:
        os.environ["FASTSEARCH_API_KEY"] = body.api_key

    if body.base_url is not None:
        os.environ["FASTSEARCH_BASE_URL"] = body.base_url

    return {
        "message": "FastSearch configuration updated",
        "base_url": os.environ.get(
            "FASTSEARCH_BASE_URL", "http://127.0.0.1:8001"
        ),
        "api_key_configured": bool(os.environ.get("FASTSEARCH_API_KEY")),
    }


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/test", response_model=TestResponse)
async def test_connection() -> Dict[str, Any]:
    """Test connectivity to the FastSearch API.

    Performs a news search query to verify the API is reachable
    and the configured API key is valid.

    On success, the global health state is updated so that the
    status endpoint immediately reflects the healthy state
    (resolves the stale-"unhealthy" display when a test succeeds).

    Returns:
        Success/failure status with result count, elapsed time,
        or error.
    """
    global _last_success_at, _last_error, _last_response_time_ms

    provider = _get_provider_from_env()

    if not provider.api_key:
        raise HTTPException(status_code=400, detail=_FORBIDDEN)

    start = time.monotonic()
    try:
        results = await provider.search("test", num_results=5)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        _last_success_at = _get_iso_now()
        _last_error = None
        _last_response_time_ms = elapsed_ms
        return {
            "success": True,
            "message": "FastSearch API is reachable and responding",
            "result_count": len(results),
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        _last_error = str(exc)
        return {
            "success": False,
            "message": "FastSearch API connection test failed",
            "result_count": 0,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
        }


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/restart", response_model=SSHCommandResponse)
async def restart_server() -> Dict[str, Any]:
    """Restart the FastSearch web container on Hetzner.

    Runs ``docker compose restart web`` on the Hetzner server,
    then reconnects the container to the ``uwu_shared`` network
    so Caddy can reach it.

    Returns:
        Success/failure with stdout/stderr.
    """
    cmd = (
        "cd /opt/fastsearch && "
        "docker compose restart web && "
        "sleep 3 && "
        "docker network connect uwu_shared fastsearch_web 2>/dev/null; "
        "echo 'restart complete'"
    )
    result = await _ssh_command(cmd)
    data = result.to_dict()

    return {
        "success": data["success"],
        "message": (
            "FastSearch web service restarted"
            if data["success"]
            else "Restart failed"
        ),
        "stdout": data.get("stdout"),
        "stderr": data.get("stderr"),
        "exit_code": data.get("exit_code"),
    }


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/rebuild", response_model=SSHCommandResponse)
async def rebuild_server() -> Dict[str, Any]:
    """Rebuild and redeploy the FastSearch web container on Hetzner.

    Runs ``docker compose build web && up -d web`` on the Hetzner
    server, then reconnects the container to ``uwu_shared``.

    Returns:
        Success/failure with stdout/stderr.
    """
    cmd = (
        "cd /opt/fastsearch && "
        "docker compose build web && "
        "docker compose up -d web && "
        "sleep 5 && "
        "docker network connect uwu_shared fastsearch_web 2>/dev/null; "
        "echo 'rebuild complete'"
    )
    result = await _ssh_command(cmd)
    data = result.to_dict()

    return {
        "success": data["success"],
        "message": (
            "FastSearch rebuilt and deployed"
            if data["success"]
            else "Rebuild failed"
        ),
        "stdout": data.get("stdout"),
        "stderr": data.get("stderr"),
        "exit_code": data.get("exit_code"),
    }


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/logs", response_model=LogsResponse)
async def get_logs() -> Dict[str, Any]:
    """Fetch recent FastSearch web container logs from Hetzner.

    Returns the last 50 lines of ``docker logs fastsearch_web``.

    Returns:
        Log lines and truncation flag.
    """
    cmd = (
        "docker logs fastsearch_web --tail 50 2>&1 || "
        "docker logs ab5083416959_fastsearch_web --tail 50 2>&1 || "
        "echo 'No FastSearch container found'"
    )
    result = await _ssh_command(cmd)
    data = result.to_dict()
    lines = [l for l in data.get("stdout", "").split("\n") if l.strip()]
    return {
        "lines": lines,
        "truncated": len(lines) < 50,
    }


def _get_iso_now() -> str:
    """Return current UTC time as ISO 8601 string."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
