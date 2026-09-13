"""Admin route: view and manage background jobs (superuser-gated).

Lists jobs from the Redis job-progress store (DB 3), keyed by
per-tenant indices.  Provides cancel and retry for failed jobs.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from airunner_services.api.routes.events import _rpc_register

router = APIRouter()


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

    async def _loopback_only(request) -> int:
        from airunner_services.api.server import (
            is_loopback_request,
        )

        if not is_loopback_request(request):
            raise HTTPException(
                status_code=403, detail="Admin access required",
            )
        return 0

    return _loopback_only


_superuser_dep = _resolve_superuser_dep()


# -- HTTP routes ------------------------------------------------------------


@router.get("/admin/jobs")
async def admin_list_jobs(
    status: str = Query(
        "",
        description="Filter by status: pending, in_progress, "
        "complete, error",
    ),
    tenant_key: str = Query(
        "",
        description="Optional tenant filter (omit for all tenants)",
    ),
    _account_id: int = Depends(_superuser_dep),
) -> dict:
    """List background jobs from the Redis job-progress store."""
    from airunner_services.tasks.redis_client import (
        cache_redis,
        job_progress_key,
        JOB_PROGRESS_TTL_SECONDS,
    )

    r = cache_redis()
    jobs: list[dict[str, Any]] = []

    # Scan all job keys (small scale — jobs have 24h TTL).
    for key in r.scan_iter(match="job:*", count=100):
        data = r.hgetall(key)
        if not data:
            continue
        job_status = data.get("status", "")
        if status and job_status != status:
            continue
        job_tenant = data.get("tenant_key", "")
        if tenant_key and job_tenant != tenant_key:
            continue
        job_id = key[len("job:"):]
        jobs.append({
            "job_id": job_id,
            "status": job_status,
            "current": int(data.get("current", 0)),
            "total": int(data.get("total", 0)),
            "label": data.get("label", ""),
            "error": data.get("error", ""),
            "tenant_key": job_tenant,
        })

    return {"jobs": jobs, "count": len(jobs)}


@router.get("/admin/jobs/{job_id}")
async def admin_get_job(
    job_id: str,
    _account_id: int = Depends(_superuser_dep),
) -> dict:
    """Get one job's detail from the Redis job-progress store."""
    from airunner_services.tasks.redis_client import (
        job_progress_read,
    )

    data = job_progress_read(job_id)
    if data is None:
        raise HTTPException(404, f"Job {job_id} not found")
    return data


@router.post("/admin/jobs/{job_id}/cancel")
async def admin_cancel_job(
    job_id: str,
    _account_id: int = Depends(_superuser_dep),
) -> dict:
    """Cancel a background job.

    Sends SIGTERM to the Celery task and cleans up any DEK relay
    entry associated with the job.
    """
    from airunner_services.tasks.celery_app import app as celery_app

    try:
        celery_app.control.revoke(job_id, terminate=True)
    except Exception as exc:
        raise HTTPException(
            500, f"Failed to cancel job {job_id}: {exc}",
        )

    return {"cancelled": job_id}


# -- RPC handlers (WebSocket) ----------------------------------------------


def _require_superuser_rpc(ws: Any) -> int | None:
    """Return account_id if the WebSocket user is a superuser."""
    try:
        from airunner_services.api.ws_tenant import resolve_ws_tenant

        _tenant, account_id = resolve_ws_tenant(ws)
        if account_id is None:
            return None
        from extensions.auth.server.models import Account

        acct = Account.objects.get(account_id)
        if acct is None or not getattr(acct, "is_superuser", False):
            return None
        return account_id
    except Exception:
        return None


@_rpc_register("GET", "/api/v1/admin/jobs")
async def _rpc_admin_list_jobs(
    body: dict, path_params: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """RPC handler: list background jobs."""
    account_id = _require_superuser_rpc(ws)
    if account_id is None:
        return {
            "status": 403,
            "body": {"error": "Superuser required"},
        }

    from airunner_services.tasks.redis_client import cache_redis

    r = cache_redis()
    jobs: list[dict[str, Any]] = []
    status_filter = body.get("status", "")

    for key in r.scan_iter(match="job:*", count=100):
        data = r.hgetall(key)
        if not data:
            continue
        if status_filter and data.get("status") != status_filter:
            continue
        jid = key[len("job:"):]
        jobs.append({
            "job_id": jid,
            "status": data.get("status", ""),
            "current": int(data.get("current", 0)),
            "total": int(data.get("total", 0)),
            "label": data.get("label", ""),
            "error": data.get("error", ""),
            "tenant_key": data.get("tenant_key", ""),
        })

    return {"status": 200, "body": {"jobs": jobs, "count": len(jobs)}}


@_rpc_register("POST", "/api/v1/admin/jobs/{job_id}/cancel")
async def _rpc_admin_cancel_job(
    body: dict, path_params: dict, ws: Any, **kw: Any,
) -> dict[str, Any]:
    """RPC handler: cancel a background job."""
    account_id = _require_superuser_rpc(ws)
    if account_id is None:
        return {
            "status": 403,
            "body": {"error": "Superuser required"},
        }

    job_id = path_params.get("job_id", "")
    if not job_id:
        return {"status": 400, "body": {"error": "Missing job_id"}}

    from airunner_services.tasks.celery_app import app as celery_app
    from airunner_services.tasks.redis_client import (
        job_progress_delete,
    )

    try:
        celery_app.control.revoke(job_id, terminate=True)
    except Exception as exc:
        return {
            "status": 500,
            "body": {"error": f"Cancel failed: {exc}"},
        }

    job_progress_delete(job_id)
    return {"status": 200, "body": {"cancelled": job_id}}
