"""Core operations for the headlesscode REST/RPC endpoints.

Shared by the FastAPI routes (``routes/headlesscode_routes.py``) and
the WebSocket RPC handlers (``routes/headlesscode_rpc.py``) so the
account-scoping, validation, and dashboard-forward logic lives in one
place.  Every operation is scoped to ``headlesscode_projects.user_id
== account_id``; sessions resolve through their owning project, so a
caller of another account's session sees the same "not found" as a
caller of a nonexistent session.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from airunner_services.database.session import session_scope
from projects.uwuchat.server.models.headlesscode_project import (
    HeadlesscodeProject,
)
from projects.uwuchat.server.models.headlesscode_session import (
    HeadlesscodeSession,
)
from projects.uwuchat.server.models.headlesscode_session_event import (
    HeadlesscodeSessionEvent,
)
from projects.uwuchat.server.routes._headlesscode_schemas import (
    to_event_out,
    to_project_out,
    to_session_out,
)

logger = logging.getLogger(__name__)


async def _resolve_workspace_root(repo_path: str) -> str:
    """Return the path session operations should actually run against.

    Asks the dashboard to resolve (creating if needed) a disposable
    worktree for *repo_path* — session launches never operate on a
    project's primary checkout directly (see session-launch.ts's
    ensureWorktree). Falls back to *repo_path* itself on any dashboard
    error (unreachable, HEADLESSCODE_DASHBOARD_WORKTREE_ROOT unset,
    etc.) so registration never hard-blocks on the dashboard being up
    — matching sync_projects_from_dashboard's existing fallback
    stance. A project registered while the dashboard was down keeps
    working against its raw repo_path until the next edit resolves it
    for real.
    """
    from projects.uwuchat.server.headlesscode_client import (
        ensure_worktree,
    )

    try:
        return await ensure_worktree(repo_path)
    except Exception:
        logger.info(
            "Headlesscode: worktree resolution unavailable for %s; "
            "using repo_path directly",
            repo_path,
        )
        return repo_path


class HeadlesscodeError(Exception):
    """Client-facing error carrying an HTTP-ish status code."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _load_project(session, account_id: int, project_id: int):
    """Return the account's project row, or None when not owned."""
    return (
        session.query(HeadlesscodeProject)
        .filter(
            HeadlesscodeProject.id == project_id,
            HeadlesscodeProject.user_id == account_id,
            HeadlesscodeProject.deleted.is_(False),
        )
        .first()
    )


def _load_session_row(session, account_id: int, hc_session_id: str):
    """Return (session_row, project), or (None, None) when unknown."""
    row = (
        session.query(HeadlesscodeSession)
        .filter(
            HeadlesscodeSession.headlesscode_session_id == hc_session_id,
        )
        .first()
    )
    if row is None:
        return None, None
    project = _load_project(session, account_id, row.project_id)
    if project is None:
        return None, None
    return row, project


def list_projects(account_id: int) -> list[dict]:
    """Return the account's registered projects, oldest first."""
    with session_scope() as session:
        rows = (
            session.query(HeadlesscodeProject)
            .filter(
                HeadlesscodeProject.user_id == account_id,
                HeadlesscodeProject.deleted.is_(False),
            )
            .order_by(HeadlesscodeProject.created_at.asc())
            .all()
        )
        return [to_project_out(r).model_dump() for r in rows]


async def create_project(
    account_id: int,
    name: str,
    repo_path: str,
    workspace_root: str,
) -> dict:
    """Register a new project, raising HeadlesscodeError on conflict."""
    name = name.strip()
    repo_path = repo_path.strip()
    workspace_root = workspace_root.strip()
    if not name or not repo_path or not workspace_root:
        raise HeadlesscodeError(
            "name, repo_path and workspace_root are all required",
        )
    # The submitted workspace_root is a form default (historically
    # mirrors repo_path) — the dashboard-resolved worktree path is
    # what session operations actually need, and it's the one thing
    # only the dashboard can compute.
    workspace_root = await _resolve_workspace_root(repo_path)
    with session_scope() as session:
        # The headlesscode clone has no setup wizard, so the tenant's
        # `users` row (users.id == account_id) may never have been
        # created — the headlesscode_projects FK targets it. Create it
        # lazily, mirroring the OAuth path (extensions/auth/server/routes.py).
        from airunner_services.database.models.user import User

        if session.query(User).get(account_id) is None:
            session.add(User(id=account_id, username=f"user_{account_id}"))
            session.flush()

        duplicate = (
            session.query(HeadlesscodeProject)
            .filter(
                HeadlesscodeProject.user_id == account_id,
                HeadlesscodeProject.name == name,
                HeadlesscodeProject.deleted.is_(False),
            )
            .first()
        )
        if duplicate is not None:
            raise HeadlesscodeError(
                f"A project named '{name}' already exists", status=409,
            )
        row = HeadlesscodeProject(
            user_id=account_id,
            name=name,
            repo_path=repo_path,
            workspace_root=workspace_root,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return to_project_out(row).model_dump()


async def update_project(
    account_id: int,
    project_id: int,
    name: str,
    repo_path: str,
    workspace_root: str,
) -> dict:
    """Update one of the account's registered projects."""
    name = name.strip()
    repo_path = repo_path.strip()
    if not name:
        raise HeadlesscodeError("name is required")
    # Only worth re-resolving when repo_path actually changed — an
    # unrelated field edit (e.g. renaming) shouldn't create a second
    # worktree for the same source repo. Read-only lookup first so the
    # (network-bound) resolution below doesn't hold a DB transaction
    # open.
    with session_scope() as session:
        row = _load_project(session, account_id, project_id)
        if row is None:
            raise HeadlesscodeError("Project not found", status=404)
        repo_path_changed = row.repo_path != repo_path
    resolved_workspace_root = (
        await _resolve_workspace_root(repo_path)
        if repo_path_changed
        else workspace_root.strip()
    )
    with session_scope() as session:
        row = _load_project(session, account_id, project_id)
        if row is None:
            raise HeadlesscodeError("Project not found", status=404)
        row.name = name
        row.repo_path = repo_path
        row.workspace_root = resolved_workspace_root
        session.commit()
        session.refresh(row)
        return to_project_out(row).model_dump()


def delete_project(account_id: int, project_id: int) -> None:
    """Soft-delete one of the account's registered projects."""
    with session_scope() as session:
        row = _load_project(session, account_id, project_id)
        if row is None:
            raise HeadlesscodeError("Project not found", status=404)
        row.deleted = True
        session.commit()


def get_session_detail(
    account_id: int,
    hc_session_id: str,
) -> Optional[dict]:
    """Return session header + event transcript, or None when unknown."""
    with session_scope() as session:
        row, project = _load_session_row(session, account_id, hc_session_id)
        if row is None:
            return None
        events = (
            session.query(HeadlesscodeSessionEvent)
            .filter(HeadlesscodeSessionEvent.session_id == row.id)
            .order_by(HeadlesscodeSessionEvent.id.asc())
            .all()
        )
        return {
            "session": to_session_out(row, project).model_dump(),
            "events": [to_event_out(e).model_dump() for e in events],
        }


def _session_is_decision_blocked(session, session_row_id: int) -> bool:
    """Return whether the session's MOST RECENT event is an unanswered
    ``ask_followup_question``/``switch_mode`` escalation.

    headlesscode's ``escalateDecision`` (see engine/executor.ts) only
    ever unblocks on ``.harness.decision-answer`` — it never looks at
    the generic mid-session-message channel at all, so routing a
    chat reply through :func:`message_session` while the session is
    blocked silently strands it until the (30-minute default) decision
    timeout. Checking the latest event lets a normal chat reply reach
    the RIGHT channel automatically.
    """
    latest = (
        session.query(HeadlesscodeSessionEvent)
        .filter(HeadlesscodeSessionEvent.session_id == session_row_id)
        .order_by(HeadlesscodeSessionEvent.id.desc())
        .first()
    )
    if latest is None:
        return False
    raw = latest.raw_event or {}
    return raw.get("type") == "decision_blocked"


async def forward_session_message(
    account_id: int,
    hc_session_id: str,
    text: str,
) -> None:
    """Forward a mid-session message to the headlesscode dashboard.

    Routed to the ``answer`` channel (see :func:`_session_is_decision_
    blocked`) when the session is currently waiting on an escalated
    question, and to the general-purpose ``message`` channel otherwise
    — both a real chat reply, from the user's perspective, but
    headlesscode's own executor only listens on the channel matching
    its current state.

    Raises HeadlesscodeError(400) on blank text, (404) on unknown or
    foreign sessions, and (502) when the dashboard forward fails.
    """
    text = text.strip()
    if not text:
        raise HeadlesscodeError("text is required")
    with session_scope() as session:
        row, project = _load_session_row(session, account_id, hc_session_id)
        if row is None:
            raise HeadlesscodeError("Session not found", status=404)
        repo_path = project.workspace_root
        decision_blocked = _session_is_decision_blocked(session, row.id)
    from projects.uwuchat.server.headlesscode_client import (
        answer_session,
        message_session,
    )

    try:
        if decision_blocked:
            await answer_session(hc_session_id, text, repo_path)
        else:
            await message_session(hc_session_id, text, repo_path)
    except Exception as exc:
        # Log the state transition only — never the repo path or body.
        logger.warning(
            "Headlesscode message forward failed: hc=%s err=%s "
            "decision_blocked=%s",
            hc_session_id,
            type(exc).__name__,
            decision_blocked,
        )
        raise HeadlesscodeError(
            "The coding agent could not accept the message right now. "
            "Try again in a moment.",
            status=502,
        )
