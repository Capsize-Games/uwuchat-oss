"""Spotify integration — server-side routes for uwuchat."""

from __future__ import annotations

import datetime
import logging
import os

import jwt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from extensions.auth.server.dependencies import require_auth

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Configuration ──────────────────────────────────────────────────────

_STATE_SECRET = os.environ.get("SPOTIFY_STATE_JWT_SECRET", "").strip()
_STATE_ALGORITHM = "HS256"
_STATE_TTL_SECONDS = int(os.environ.get("SPOTIFY_STATE_TTL", "600"))  # 10 min

_INSTANCE_URL = os.environ.get(
    "AIRUNNER_SITE_URL", "http://localhost:5173",
).strip().rstrip("/")


# ── Schemas ────────────────────────────────────────────────────────────


class GenerateStateRequest(BaseModel):
    """Request body for ``POST /generate-state``."""

    code_verifier: str


class GenerateStateResponse(BaseModel):
    """Response body for ``POST /generate-state``."""

    state: str


# ── Endpoints ──────────────────────────────────────────────────────────


@router.post(
    "/generate-state",
    response_model=GenerateStateResponse,
    summary="Generate a signed Spotify OAuth state JWT",
)
async def generate_state(
    body: GenerateStateRequest,
    account_id: int = Depends(require_auth),
) -> GenerateStateResponse:
    """Generate a signed JWT state token for the Spotify OAuth flow.

    The state token contains the user's account ID and the PKCE
    code verifier.  FastSearch validates this JWT on the OAuth
    callback to associate the Spotify connection with the user.

    Requires authentication.
    """
    if not _STATE_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "Spotify integration is not configured. "
                "Set SPOTIFY_STATE_JWT_SECRET to enable."
            ),
        )

    if not body.code_verifier:
        raise HTTPException(
            status_code=400,
            detail="code_verifier is required",
        )

    import secrets as _secrets

    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": account_id,
        "code_verifier": body.code_verifier,
        "uwuchat_instance": _INSTANCE_URL,
        "nonce": _secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_STATE_TTL_SECONDS),
        "type": "spotify_oauth_state",
    }

    state = jwt.encode(
        payload,
        _STATE_SECRET,
        algorithm=_STATE_ALGORITHM,
    )
    return GenerateStateResponse(state=state)
