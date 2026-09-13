"""Thin HTTP client for the headlesscode dashboard control plane.

Wraps the routes exposed by ``headlesscode dashboard`` (Phase 2 of
plans/uwuchat-headlesscode-live-session-integration.md):

- ``POST /api/session/start``              launch a detached session
- ``GET  /api/session/:id/events?since=``  poll a session's event feed
- ``POST /api/session/:id/pause|resume|answer``  control a session
- ``POST /api/session/:id/message``        inject a mid-session message

Bearer-token auth via ``HEADLESSCODE_DASHBOARD_TOKEN``; base URL from
``HEADLESSCODE_DASHBOARD_URL`` (default ``http://127.0.0.1:4390``).
No business logic here — HTTP wrapper only; callers (Phase 3+) own
polling, persistence, and UI concerns.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from airunner_services.conf import settings

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 30.0
_DEFAULT_DASHBOARD_URL = "http://127.0.0.1:4390"


def _dashboard_url() -> str:
    """Return the dashboard base URL without a trailing slash."""
    url = os.environ.get("HEADLESSCODE_DASHBOARD_URL", "").strip()
    if not url:
        url = str(settings.get("HEADLESSCODE_DASHBOARD_URL", "") or "")
    if not url:
        url = _DEFAULT_DASHBOARD_URL
    return url.rstrip("/")


def _bearer_token() -> str:
    """Return the configured dashboard bearer token, if any."""
    token = os.environ.get("HEADLESSCODE_DASHBOARD_TOKEN", "").strip()
    if not token:
        token = str(settings.get("HEADLESSCODE_DASHBOARD_TOKEN", "") or "")
    return token.strip()


def _headers() -> dict[str, str]:
    """Return auth headers; empty when no token is configured."""
    token = _bearer_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


async def list_projects() -> list[dict[str, Any]]:
    """Return the dashboard's registered-project entries.

    Each entry carries the dashboard's view of the project: ``key``,
    ``path`` (filesystem path), ``registered``, ``exists``, and —
    since Phase 1 of plans/uwuchat-host-executor-with-consent.md —
    ``gitOwnerName`` (the GitHub "owner/name" from the repo's origin
    remote, e.g. ``<your-org>/airunnerweb``).  This is the
    authoritative owner source for ``gh`` because only the dashboard
    (which manages the worktrees) can read the git remote.
    """
    body = await _get("/api/projects", params={"all": "1"})
    return list(body.get("projects") or [])


async def start_session(
    repo: str, task: str, mode: str | None = None
) -> dict[str, Any]:
    """Launch a detached headlesscode session for *repo* and *task*.

    Returns the dashboard's ``{sessionId, pid, workspace, mode}`` body.
    """
    payload: dict[str, Any] = {"repo": repo, "task": task}
    if mode:
        payload["mode"] = mode
    return await _post("/api/session/start", json=payload)


async def get_session_events(
    session_id: str, repo: str, since: int = 0
) -> dict[str, Any]:
    """Return *session_id*'s events newer than offset *since*.

    Returns the dashboard's ``{sessionId, events, nextOffset}`` body.
    """
    params: dict[str, Any] = {"since": since, "repo": repo}
    return await _get(
        f"/api/session/{session_id}/events", params=params
    )


async def pause_session(session_id: str, repo: str) -> dict[str, Any]:
    """Pause *session_id* between iterations."""
    return await _post(
        f"/api/session/{session_id}/pause",
        params={"repo": repo},
    )


async def resume_session(session_id: str, repo: str) -> dict[str, Any]:
    """Resume a paused *session_id*."""
    return await _post(
        f"/api/session/{session_id}/resume",
        params={"repo": repo},
    )


async def answer_session(
    session_id: str, answer: str, repo: str
) -> dict[str, Any]:
    """Answer *session_id*'s escalated ask_followup_question."""
    return await _post(
        f"/api/session/{session_id}/answer",
        json={"answer": answer},
        params={"repo": repo},
    )


async def message_session(
    session_id: str, text: str, repo: str
) -> dict[str, Any]:
    """Inject *text* as a user message into running *session_id*.

    headlesscode's policy is overwrite-with-latest: a second injection
    before the first is picked up silently replaces it (no queue).
    """
    return await _post(
        f"/api/session/{session_id}/message",
        json={"text": text},
        params={"repo": repo},
    )


async def ensure_worktree(repo: str) -> str:
    """Return the disposable worktree path *repo*'s sessions should run
    against, creating it on the dashboard's side if needed.

    Called once at project registration (see headlesscode_service.py's
    create_project/update_project), not per-launch — the caller stores
    the result and reuses it for every session/poll/pause/resume/
    message operation on that project. Raises on any dashboard error
    (including a 501 when ``HEADLESSCODE_DASHBOARD_WORKTREE_ROOT``
    isn't configured); callers fall back to *repo* itself rather than
    blocking registration on the dashboard's availability.
    """
    body = await _post("/api/projects/ensure-worktree", json={"repo": repo})
    return str(body["workspace"])


async def execute_tool(
    workspace: str, name: str, args: dict[str, Any],
) -> dict[str, Any]:
    """Run one headlesscode executor tool synchronously and return the result.

    ``name``/``args`` are passed straight through to the dashboard's
    ``POST /api/tool/execute`` (see headlesscode's ``tool-exec.ts``) —
    the tool set, argument schemas, permission gating, and workspace
    path safety are all implemented harness-side. Returns the
    dashboard body ``{ok, isError, content}``. Raises on transport or
    HTTP errors, like every other client method.
    """
    return await _post(
        "/api/tool/execute",
        json={"workspace": workspace, "name": name, "args": args},
    )


async def _get(
    url: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Perform one authenticated GET and return the JSON body."""
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.get(
            _dashboard_url() + url,
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()


async def _post(
    url: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Perform one authenticated POST and return the JSON body."""
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        resp = await client.post(
            _dashboard_url() + url,
            json=json,
            params=params,
            headers=_headers(),
        )
        resp.raise_for_status()
        return resp.json()
