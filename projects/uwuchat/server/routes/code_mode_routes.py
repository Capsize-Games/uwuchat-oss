"""Code-mode toggle API — admin-only per-conversation switch.

Mounted at ``/api/v1/uwuchat/code-mode/{conversation_id}``. Scoped to
conversations owned by the calling superuser — code mode is a
developer-facing toggle for the admin's own coding-task
conversations, not a user-facing feature (see code_mode_service.py).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from airunner_services.database.models.conversation import Conversation
from extensions.auth.server.dependencies import require_superuser
from projects.uwuchat.server.code_mode_service import (
    get_code_mode_slug,
    is_code_mode_enabled,
    set_code_mode,
)

router = APIRouter()


class CodeModeOut(BaseModel):
    """Response body for both the get and set endpoints."""

    enabled: bool
    mode: str


class CodeModeIn(BaseModel):
    """Request body for the set endpoint."""

    enabled: bool
    mode: str | None = None


def _owned_conversation(
    conversation_id: int, account_id: int
) -> Conversation:
    """Return the caller's own conversation, or raise 404."""
    conv = Conversation.objects.get(conversation_id)
    if conv is None or conv.user_id != account_id:
        raise HTTPException(404, "Conversation not found")
    return conv


@router.get(
    "/code-mode/{conversation_id}", response_model=CodeModeOut
)
async def get_code_mode_route(
    conversation_id: int,
    account_id: int = Depends(require_superuser),
) -> CodeModeOut:
    """Return whether code mode is on for one of the admin's own
    conversations."""
    conv = _owned_conversation(conversation_id, account_id)
    return CodeModeOut(
        enabled=is_code_mode_enabled(conv), mode=get_code_mode_slug(conv),
    )


@router.put(
    "/code-mode/{conversation_id}", response_model=CodeModeOut
)
async def set_code_mode_route(
    conversation_id: int,
    payload: CodeModeIn,
    account_id: int = Depends(require_superuser),
) -> CodeModeOut:
    """Turn code mode on/off for one of the admin's own conversations."""
    _owned_conversation(conversation_id, account_id)
    try:
        enabled, mode = set_code_mode(
            conversation_id, payload.enabled, slug=payload.mode,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return CodeModeOut(enabled=enabled, mode=mode)
