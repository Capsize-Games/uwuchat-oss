"""OAuth capabilities endpoint — reports which providers are configured.

Mounted at ``/api/v1/auth``.  Returns a public (non-secret) map of
``provider → bool`` so the frontend can decide whether to render
OAuth sign-in buttons without leaking credential values.
"""

from __future__ import annotations

from fastapi import APIRouter

from extensions.auth.server.oauth import OAUTH_CONFIGURED as GOOGLE_CONFIGURED
from extensions.auth.server.twitch_oauth import (
    OAUTH_CONFIGURED as TWITCH_CONFIGURED,
)

router = APIRouter()


# nosemgrep: missing-auth-dependency (public OAuth capabilities endpoint)
@router.get("/oauth/capabilities", summary="OAuth provider status")
async def oauth_capabilities() -> dict:
    """Return which OAuth providers are currently configured.

    Does **not** leak ``CLIENT_ID``, ``CLIENT_SECRET``, or any other
    credential values — only a boolean per provider.
    """
    return {
        "google": GOOGLE_CONFIGURED,
        "twitch": TWITCH_CONFIGURED,
    }
