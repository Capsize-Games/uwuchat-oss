"""UwUChat headlesscode REST API — project registry, sessions, injection.

Mounted at ``/api/v1/uwuchat/headlesscode``. Thin FastAPI wrapper over
:mod:`headlesscode_service`; every endpoint is gated by
:func:`require_auth`.  WebSocket clients reach the same operations via
the RPC handlers in :mod:`headlesscode_rpc` — the service layer owns
all account-scoping and validation so the two transports can't drift.
"""

from __future__ import annotations

import importlib

from fastapi import APIRouter, Depends, HTTPException

from extensions.auth.server.dependencies import require_auth
from projects.uwuchat.server import headlesscode_service as hc
from projects.uwuchat.server.headlesscode_service import HeadlesscodeError
from projects.uwuchat.server.routes._headlesscode_schemas import (
    MessageIn,
    MessageOut,
    ProjectIn,
    ProjectListOut,
    ProjectOut,
    SessionDetailOut,
)

router = APIRouter()


def _error(exc: HeadlesscodeError) -> HTTPException:
    """Map a service error onto an HTTP response."""
    return HTTPException(status_code=exc.status, detail=exc.message)


@router.get("/projects", response_model=ProjectListOut)
async def list_projects(
    account_id: int = Depends(require_auth),
) -> ProjectListOut:
    """Return the authenticated user's registered projects."""
    return ProjectListOut(projects=hc.list_projects(account_id))


@router.post("/projects", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectIn,
    account_id: int = Depends(require_auth),
) -> ProjectOut:
    """Register a new project for the authenticated user."""
    try:
        return ProjectOut(**await hc.create_project(
            account_id,
            payload.name,
            payload.repo_path,
            payload.workspace_root,
        ))
    except HeadlesscodeError as exc:
        raise _error(exc) from exc


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int,
    payload: ProjectIn,
    account_id: int = Depends(require_auth),
) -> ProjectOut:
    """Update one of the user's registered projects."""
    try:
        return ProjectOut(**await hc.update_project(
            account_id, project_id,
            payload.name, payload.repo_path, payload.workspace_root,
        ))
    except HeadlesscodeError as exc:
        raise _error(exc) from exc


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    account_id: int = Depends(require_auth),
) -> None:
    """Soft-delete one of the user's registered projects."""
    try:
        hc.delete_project(account_id, project_id)
    except HeadlesscodeError as exc:
        raise _error(exc) from exc


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
async def get_session_detail(
    session_id: str,
    account_id: int = Depends(require_auth),
) -> SessionDetailOut:
    """Return one session's header plus its durable event transcript."""
    detail = hc.get_session_detail(account_id, session_id)
    if detail is None:
        raise HTTPException(404, "Session not found")
    return SessionDetailOut(**detail)


@router.post("/sessions/{session_id}/message", response_model=MessageOut)
async def inject_session_message(
    session_id: str,
    payload: MessageIn,
    account_id: int = Depends(require_auth),
) -> MessageOut:
    """Forward a mid-session message to a running headlesscode session.

    Thin synchronous forward to the dashboard's
    ``POST /api/session/:id/message``. headlesscode's injection policy
    is overwrite-with-latest — a second message sent before the first
    is picked up silently replaces it (no queue), so the client keeps
    the send affordance disabled until the ``message_injected`` event
    confirms delivery.
    """
    try:
        await hc.forward_session_message(
            account_id, session_id, payload.text,
        )
    except HeadlesscodeError as exc:
        raise _error(exc) from exc
    return MessageOut(ok=True, session_id=session_id)


# Importing by name (not binding it) runs the @_rpc_register decorators
# in headlesscode_rpc.py — same convention as email/routes.py.
importlib.import_module(f"{__package__}.headlesscode_rpc")
