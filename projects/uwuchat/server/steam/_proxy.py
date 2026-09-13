"""Steam OpenID helpers — JWT state tokens, validation, Steam ID extraction."""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any

import jwt

logger = logging.getLogger(__name__)

# Shared JWT secret for Steam OpenID state tokens.
# Falls back to AIRUNNER_JWT_SECRET for dev convenience.
_JWT_SECRET = (
    os.environ.get("STEAM_STATE_JWT_SECRET", "").strip()
    or os.environ.get("AIRUNNER_JWT_SECRET", "").strip()
)
_JWT_ALGORITHM = "HS256"
_JWT_TTL_SECONDS = int(os.environ.get("STEAM_STATE_TTL", "600"))


def _steam_state_jwt(account_id: int, mode: str = "link") -> str | None:
    """Generate a short-lived JWT for the Steam OpenID state parameter."""
    if not _JWT_SECRET:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": account_id,
        "mode": mode,
        "iat": now,
        "exp": now + datetime.timedelta(seconds=_JWT_TTL_SECONDS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def _decode_state_jwt(
    state: str,
) -> tuple[int | None, str]:
    """Decode a Steam OpenID state JWT.

    Returns ``(user_id, mode)``. ``user_id`` is ``None`` on decode failure.
    """
    try:
        payload = jwt.decode(
            state, _JWT_SECRET, algorithms=[_JWT_ALGORITHM],
        )
        return (
            int(payload["user_id"]),
            payload.get("mode", "link"),
        )
    except Exception:
        return None, "link"


from airunner_services.api.ws_tenant import resolve_ws_tenant


def require_self(
    account_id: int,
    path_params: dict,
    param: str,
) -> dict[str, Any] | None:
    """Return an error dict if *account_id* doesn't match the URL param."""
    raw = path_params.get(param, "")
    try:
        target_id = int(raw)
    except (ValueError, TypeError):
        return {"status": 400, "body": {"error": f"Invalid {param}"}}
    if target_id != account_id:
        return {"status": 403, "body": {"error": "Forbidden"}}
    return None


def require_ws_auth(
    kw: dict[str, Any],
) -> tuple[Any, int | None, dict | None]:
    """Resolve auth from an RPC handler's ``**kw``.

    Returns ``(ws, account_id, error)`` — exactly one of *account_id* or
    *error* is not None.
    """
    ws = kw.get("ws")
    if ws is None:
        return None, None, {
            "status": 400,
            "body": {"error": "WebSocket required"},
        }
    _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return ws, None, {
            "status": 401,
            "body": {"error": "Authentication required"},
        }
    return ws, account_id, None


# ---- OpenID Helpers ------------------------------------------------------


async def validate_openid(params: dict[str, str]) -> bool:
    """Perform back-channel OpenID validation with Steam.

    POSTs the OpenID response params back to Steam with
    ``openid.mode=check_authentication`` and checks that Steam
    responds with ``is_valid:true``.
    """
    import aiohttp

    validation_params = dict(params)
    validation_params["openid.mode"] = "check_authentication"

    url = "https://steamcommunity.com/openid/login"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=validation_params) as resp:
                text = await resp.text()
                resp.raise_for_status()
                result = "is_valid:true" in text
                if not result:
                    logger.warning(
                        "Steam validation failed. "
                        "Response (first 200 chars): %s",
                        text[:200],
                    )
                return result
    except Exception as exc:
        logger.warning(
            "Steam OpenID validation HTTP error: %s", exc,
        )
        return False


def extract_steam_id(claimed_id: str) -> str | None:
    """Extract the Steam64 ID from an OpenID claimed_id URL.

    ``https://steamcommunity.com/openid/id/76561197960287930``
    returns ``76561197960287930``.
    """
    from urllib.parse import urlparse as _urlparse

    if not claimed_id:
        return None
    parsed = _urlparse(claimed_id)
    path_parts = parsed.path.rstrip("/").split("/")
    if path_parts:
        return path_parts[-1]
    return None
