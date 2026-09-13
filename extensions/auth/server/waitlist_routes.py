"""Waitlist REST API — mounted at /api/v1/auth/waitlist.

Endpoints:
  POST /join           — public, join the waitlist
  GET  /admin/list     — superuser, queue status
  POST /admin/release  — superuser, release invite batch
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from extensions.auth.server.dependencies import require_superuser
from extensions.auth.server.email import send_waitlist_confirmation_email
from extensions.auth.server.limiter import limiter
from extensions.auth.server.waitlist_service import (
    issue_invites,
    join_waitlist,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_background_tasks: set[asyncio.Task] = set()

SITE_URL = os.environ.get(
    "AIRUNNER_SITE_URL", "http://localhost:5173",
).strip().rstrip("/")


# ── Request / Response schemas ──────────────────────────────────────


class JoinRequest(BaseModel):
    email: str


class JoinResponse(BaseModel):
    joined: bool


class WaitlistEntryOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    status: str  # waiting | invited | converted
    invited_at: str | None = None
    converted_at: str | None = None


class WaitlistListResponse(BaseModel):
    entries: list[WaitlistEntryOut]
    total: int
    waiting: int
    invited: int
    converted: int


class ReleaseRequest(BaseModel):
    count: int


class ReleaseResponse(BaseModel):
    released: int
    emails: list[str]


# ── Public endpoints ────────────────────────────────────────────────


# nosemgrep: missing-auth-dependency (public waitlist join endpoint)
@router.post(
    "/join",
    summary="Join the waitlist for early access",
    response_model=JoinResponse,
)
@limiter.limit("5/minute")
async def waitlist_join(request: Request, body: JoinRequest) -> JoinResponse:
    """Register interest. Always returns success — the caller cannot
    tell whether the email was already on the list."""
    ip = request.client.host if request.client else None
    join_waitlist(body.email.strip().lower(), ip)

    # Fire-and-forget confirmation email.
    task = asyncio.ensure_future(
        asyncio.to_thread(
            send_waitlist_confirmation_email,
            body.email.strip().lower(),
        ),
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return JoinResponse(joined=True)


# ── Admin endpoints ─────────────────────────────────────────────────


# nosemgrep: missing-auth-dependency (public waitlist join endpoint)
@router.get(
    "/admin/list",
    summary="List waitlist entries (superuser only)",
    response_model=WaitlistListResponse,
)
@limiter.limit("60/minute")
async def waitlist_admin_list(
    request: Request,
    _admin_id: int = Depends(require_superuser),
) -> WaitlistListResponse:
    """Return all waitlist entries with counts by status."""
    from airunner_services.database.session import public_session_scope
    from extensions.auth.server.waitlist_entry import WaitlistEntry

    with public_session_scope() as session:
        rows = (
            session.query(WaitlistEntry)
            .order_by(WaitlistEntry.created_at.asc())
            .all()
        )
        entries: list[WaitlistEntryOut] = []
        waiting = invited = converted = 0
        for r in rows:
            if r.converted_account_id is not None:
                status = "converted"
                converted += 1
            elif r.token_hash is not None:
                status = "invited"
                invited += 1
            else:
                status = "waiting"
                waiting += 1
            entries.append(WaitlistEntryOut(
                id=r.id,
                email=r.email,
                status=status,
                invited_at=(
                    r.invited_at.isoformat() if r.invited_at else None
                ),
                converted_at=(
                    r.converted_at.isoformat() if r.converted_at else None
                ),
            ))
        session.expunge_all()

    return WaitlistListResponse(
        entries=entries,
        total=len(entries),
        waiting=waiting,
        invited=invited,
        converted=converted,
    )


# nosemgrep: missing-auth-dependency (public waitlist join endpoint)
@router.post(
    "/admin/release",
    summary="Release a batch of invite tokens (superuser only)",
    response_model=ReleaseResponse,
)
@limiter.limit("30/minute")
async def waitlist_admin_release(
    request: Request,
    body: ReleaseRequest,
    _admin_id: int = Depends(require_superuser),
) -> ReleaseResponse:
    """Issue *count* invite tokens to the oldest uninvited entries and
    send invitation emails."""
    if body.count < 1:
        raise HTTPException(400, "count must be at least 1")

    entries = issue_invites(body.count)

    released_emails: list[str] = []
    for entry in entries:
        raw = getattr(entry, "_raw_token", None)
        if raw is None:
            continue
        released_emails.append(entry.email)
        register_url = (
            f"{SITE_URL}/register?waitlist_token={raw}"
        )
        task = asyncio.ensure_future(
            asyncio.to_thread(
                send_waitlist_invite_email,
                entry.email,
                register_url,
            ),
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return ReleaseResponse(
        released=len(released_emails),
        emails=released_emails,
    )


# ── Invite email (private, used by admin release only) ─────────────


def send_waitlist_invite_email(
    to_email: str,
    register_url: str,
) -> bool:
    """Send the "you're off the waitlist" invitation email."""
    from extensions.auth.server.email import send_email

    subject = "You're off the waitlist — create your account"
    html_body = (
        f"<p>You've been invited to create your account.</p>"
        f"<p><a href=\"{register_url}\">Create your account</a></p>"
        f"<p>This link expires in 7 days.</p>"
    )
    text_body = (
        f"You've been invited to create your account.\n\n"
        f"Visit {register_url} to sign up.\n\n"
        f"This link expires in 7 days.\n"
    )
    return send_email(to_email, subject, html_body, text_body)
