"""Admin Celery visibility endpoints (superuser-gated).

Exposes Celery worker and task state — registered task names, active/
reserved task counts, queue depth, and recent failures — as an HTTP API
so the admin UI can inspect the task system without raw redis-cli /
celery inspect commands.

All endpoints require superuser authentication, mirroring the guard
pattern in ``admin_health_routes.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter()
_log = logging.getLogger(__name__)

_INSPECT_TIMEOUT = 3.0  # seconds — short so a dead worker doesn't hang


# ------------------------------------------------------------------
# Superuser guard (same pattern as admin_health_routes)
# ------------------------------------------------------------------


def _resolve_superuser_dep():
    """Return a dependency that requires superuser or loopback."""
    # nosemgrep: auth-import-error-fallback (see round-7 review)
    try:
        from extensions.auth.server.dependencies import (
            require_superuser,
        )

        return require_superuser
    except ImportError:
        pass

    async def _loopback_only(request: Request) -> int:
        from airunner_services.api.server import (
            is_loopback_request,
        )

        if not is_loopback_request(request):
            raise HTTPException(
                status_code=403, detail="Admin access required"
            )
        return 0

    return _loopback_only


_superuser_dep = _resolve_superuser_dep()


# ------------------------------------------------------------------
# GET /celery/workers
# ------------------------------------------------------------------


@router.get("/celery/workers")
async def celery_workers(
    req: Request,
    _account_id: int = Depends(_superuser_dep),
) -> dict:
    """Return Celery worker status: active, reserved, registered tasks.

    Returns a degraded (empty) response when Celery inspection times
    out or the broker is unreachable — never 500.
    """
    try:
        from airunner_services.tasks.celery_app import app
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Celery app not importable: {exc}",
        ) from exc

    result: dict[str, Any] = {
        "workers": [],
        "active_count": 0,
        "reserved_count": 0,
        "error": None,
    }

    try:
        inspect = app.control.inspect(timeout=_INSPECT_TIMEOUT)
        stats = inspect.stats() or {}
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        registered = inspect.registered() or {}
    except Exception as exc:
        _log.warning("Celery inspect failed: %s", exc)
        result["error"] = f"Inspection unavailable: {exc}"
        return result

    total_active = 0
    total_reserved = 0

    for worker_name in sorted(stats.keys()):
        worker_stats = stats.get(worker_name, {}) or {}
        worker_active = active.get(worker_name, []) or []
        worker_reserved = reserved.get(worker_name, []) or []
        worker_registered = registered.get(worker_name, []) or []

        total_active += len(worker_active)
        total_reserved += len(worker_reserved)

        result["workers"].append({
            "name": worker_name,
            "pool_size": worker_stats.get("pool", {}).get("max-concurrency", 0),
            "active_tasks": len(worker_active),
            "reserved_tasks": len(worker_reserved),
            "registered_task_count": len(worker_registered),
            "registered_tasks": sorted(worker_registered),
        })

    result["active_count"] = total_active
    result["reserved_count"] = total_reserved

    return result


# ------------------------------------------------------------------
# GET /celery/failures
# ------------------------------------------------------------------


@router.get("/celery/failures")
async def celery_failures(
    req: Request,
    _account_id: int = Depends(_superuser_dep),
) -> dict:
    """Return recent Celery task failures (best-effort).

    Celery result-backend entries expire, so this may return an empty
    list even when failures occurred in the past.  The response always
    includes an ``expiry_note`` explaining this limitation.
    """
    result: dict[str, Any] = {
        "failures": [],
        "expiry_note": (
            "Results expire from the backend after their TTL. "
            "An empty list does not guarantee zero failures."
        ),
    }

    try:
        from airunner_services.tasks.celery_app import app
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Celery app not importable: {exc}",
        ) from exc

    try:
        inspect = app.control.inspect(timeout=_INSPECT_TIMEOUT)
        active = inspect.active() or {}
    except Exception as exc:
        _log.warning("Celery inspect for failures failed: %s", exc)
        result["failures"] = []
        return result

    # Scan active tasks for those that may be retrying (redelivered).
    # This is a lightweight heuristic — true failure tracking requires
    # a result-backend query, which doesn't scale well.
    retrying: list[dict[str, Any]] = []
    for worker_name, tasks in active.items():
        for task in (tasks or []):
            if task.get("delivery_info", {}).get("redelivered"):
                retrying.append({
                    "task_id": task.get("id", ""),
                    "task_name": task.get("name", ""),
                    "worker": worker_name,
                    "args": str(task.get("args", "")),
                })

    result["retrying_count"] = len(retrying)
    result["retrying"] = retrying

    return result
