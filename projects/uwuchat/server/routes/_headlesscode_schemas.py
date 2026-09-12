"""Pydantic request/response schemas for the headlesscode REST API.

Kept in their own module so ``headlesscode_routes.py`` stays under
CLAUDE.md's 250-line file limit. These are API wire schemas, not ORM
models — they serialize ``headlesscode_projects`` /
``headlesscode_sessions`` / ``headlesscode_session_events`` rows for
the client panels and session cards. The ``_to_*_out`` mappers below
convert ORM rows into the wire schemas.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from projects.uwuchat.server.models.headlesscode_project import (
    HeadlesscodeProject,
)
from projects.uwuchat.server.models.headlesscode_session import (
    HeadlesscodeSession,
)
from projects.uwuchat.server.models.headlesscode_session_event import (
    HeadlesscodeSessionEvent,
)


class ProjectIn(BaseModel):
    """Create/update payload for one registered project."""

    name: str
    repo_path: str
    workspace_root: str


class ProjectOut(BaseModel):
    """Serialised registered project for the client panel."""

    id: int
    name: str
    repo_path: str
    workspace_root: str
    created_at: Optional[str] = None


class ProjectListOut(BaseModel):
    """List of the user's registered projects."""

    projects: list[ProjectOut]


class SessionOut(BaseModel):
    """Serialised headlesscode session for a session card."""

    headlesscode_session_id: str
    project_id: int
    project_name: Optional[str] = None
    status: str
    task_description: Optional[str] = None
    mode: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SessionEventOut(BaseModel):
    """One event row from a session's durable transcript."""

    id: int
    chat_block_kind: Optional[str] = None
    raw_event: dict
    created_at: Optional[str] = None


class SessionDetailOut(BaseModel):
    """Session header plus durable event transcript for a card."""

    session: SessionOut
    events: list[SessionEventOut]


class MessageIn(BaseModel):
    """Body for the mid-session message-injection endpoint."""

    text: str


class MessageOut(BaseModel):
    """Response for a message-injection forward."""

    ok: bool
    session_id: str


def to_project_out(row: HeadlesscodeProject) -> ProjectOut:
    """Map a project ORM row to the output schema."""
    return ProjectOut(
        id=row.id,
        name=row.name,
        repo_path=row.repo_path,
        workspace_root=row.workspace_root,
        created_at=(
            row.created_at.isoformat() if row.created_at else None
        ),
    )


def to_session_out(
    row: HeadlesscodeSession, project: Any,
) -> SessionOut:
    """Map a session ORM row (plus owner) to the output schema."""
    return SessionOut(
        headlesscode_session_id=row.headlesscode_session_id,
        project_id=row.project_id,
        project_name=project.name if project else None,
        status=row.status,
        task_description=row.task_description,
        mode=row.mode,
        created_at=(
            row.created_at.isoformat() if row.created_at else None
        ),
        updated_at=(
            row.updated_at.isoformat() if row.updated_at else None
        ),
    )


def to_event_out(row: HeadlesscodeSessionEvent) -> SessionEventOut:
    """Map one event row to the output schema."""
    return SessionEventOut(
        id=row.id,
        chat_block_kind=row.chat_block_kind,
        raw_event=row.raw_event or {},
        created_at=(
            row.created_at.isoformat() if row.created_at else None
        ),
    )
