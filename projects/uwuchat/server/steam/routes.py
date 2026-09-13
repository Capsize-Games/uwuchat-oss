"""Steam integration — OpenID auth + local storage."""

from __future__ import annotations

import datetime
import logging
import os
import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from airunner_services.api.routes.events import _rpc_register
from airunner_services.api.ws_tenant import resolve_ws_tenant
from airunner_services.database.models.steam_connection import SteamConnection
from airunner_services.database.session import session_scope
from extensions.auth.server.dependencies import require_auth

from ._proxy import (
    _decode_state_jwt,
    _steam_state_jwt,
    extract_steam_id,
    validate_openid,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---- Configuration -------------------------------------------------------

_STATE_SECRET = (
    os.environ.get("STEAM_STATE_JWT_SECRET", "").strip()
    or os.environ.get("AIRUNNER_JWT_SECRET", "").strip()
)

# Only allow skipping OpenID back-channel validation when an explicit
# opt-in env var is set AND the deployment mode is not production.
# We never silently disable validation just because a secret is unset.
_DEPLOYMENT_MODE = os.environ.get(
    "AIRUNNER_DEPLOYMENT_MODE", "development",
).lower()
_SKIP_VALIDATION = (
    os.environ.get("AIRUNNER_ALLOW_STEAM_SKIP_VALIDATION", "") == "1"
    and _DEPLOYMENT_MODE != "production"
)

_INSTANCE_URL = os.environ.get(
    "AIRUNNER_SITE_URL", "http://localhost:5173",
).strip().rstrip("/")

_STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"


_REFRESH_INTERVAL_HOURS = 4
_MAX_CACHED_ACHIEVEMENTS = 10


async def _refresh_steam_profile(
    steam_id: str,
    conn: SteamConnection,
    session: Any,
) -> None:
    """Re-fetch Steam profile + games and update *conn* in-place."""
    import json as _json
    from ._webapi import (
        get_friend_list,
        get_owned_games,
        get_player_summaries,
        get_recently_played_games,
        get_steam_level,
    )

    player = await get_player_summaries(steam_id)
    level = await get_steam_level(steam_id)
    games_data = await get_owned_games(steam_id)
    friend_count = await get_friend_list(steam_id)
    recent = await get_recently_played_games(steam_id)

    _apply_player_summary(conn, player, level)
    _apply_games_data(conn, games_data, _json)
    if recent is not None:
        conn.recently_played_json = _json.dumps(recent)
    conn.friend_count = friend_count
    conn.last_scraped_at = datetime.datetime.utcnow()
    session.commit()


def _apply_player_summary(
    conn: SteamConnection,
    player: dict[str, Any] | None,
    level: int | None,
) -> None:
    """Copy Steam player summary fields onto *conn*."""
    if player is None:
        return
    conn.display_name = player.get("personaname")
    conn.avatar_url = player.get("avatarfull")
    conn.profile_url = player.get("profileurl")
    conn.persona_state = player.get("personastate")
    last_logoff = player.get("lastlogoff")
    if last_logoff:
        conn.last_logoff = datetime.datetime.utcfromtimestamp(
            last_logoff,
        )
    time_created = player.get("timecreated")
    if time_created:
        conn.time_created = datetime.datetime.utcfromtimestamp(
            time_created,
        )
    conn.steam_level = level


def _apply_games_data(
    conn: SteamConnection,
    games_data: dict[str, Any] | None,
    _json: Any,
) -> None:
    """Copy owned-games fields onto *conn*."""
    if games_data is None:
        return
    conn.total_games_owned = games_data["game_count"]
    conn.total_playtime_minutes = games_data["total_playtime_minutes"]
    top = games_data.get("top_games", [])
    if top:
        conn.top_games_json = _json.dumps(top)
    all_g = games_data.get("all_games", [])
    if all_g:
        conn.all_games_json = _json.dumps(all_g)


def _is_stale(conn: SteamConnection) -> bool:
    """Return True if Steam data hasn't been refreshed recently."""
    if conn.last_scraped_at is None:
        return True
    age = datetime.datetime.utcnow() - conn.last_scraped_at
    return age > datetime.timedelta(hours=_REFRESH_INTERVAL_HOURS)


def _get_cached_achievements(
    conn: SteamConnection,
    appid: int,
) -> dict[str, Any] | None:
    """Return cached achievement data for *appid* if fresh."""
    if not conn.achievements_cache_json:
        return None
    try:
        import json as _json
        cache = _json.loads(conn.achievements_cache_json)
    except (ValueError, TypeError):
        return None
    entry = cache.get(str(appid))
    if not entry:
        return None
    fetched_at_str = entry.get("fetched_at", "")
    try:
        fetched_at = datetime.datetime.fromisoformat(
            fetched_at_str,
        )
    except (ValueError, TypeError):
        return None
    age = datetime.datetime.utcnow() - fetched_at
    if age > datetime.timedelta(hours=_REFRESH_INTERVAL_HOURS):
        return None
    return entry.get("data")


def _cache_achievements(
    conn: SteamConnection,
    appid: int,
    data: dict[str, Any],
    session: Any,
) -> None:
    """Store achievement data in the cache column."""
    import json as _json
    try:
        cache = (
            _json.loads(conn.achievements_cache_json)
            if conn.achievements_cache_json
            else {}
        )
    except (ValueError, TypeError):
        cache = {}
    key = str(appid)
    cache[key] = {
        "fetched_at": datetime.datetime.utcnow().isoformat(),
        "data": data,
    }
    # Keep only the N most recent entries
    if len(cache) > _MAX_CACHED_ACHIEVEMENTS:
        sorted_keys = sorted(
            cache.keys(),
            key=lambda k: cache[k].get("fetched_at", ""),
            reverse=True,
        )
        cache = {k: cache[k] for k in sorted_keys[:_MAX_CACHED_ACHIEVEMENTS]}
    conn.achievements_cache_json = _json.dumps(cache)
    session.commit()


# ---- Helpers -------------------------------------------------------------


async def _handle_auth_mode(
    steam_id: str,
    site_url: str,
    login_url: str,
    settings_url: str,
) -> RedirectResponse:
    """Sign in or sign up with Steam.

    Looks up an existing account by ``steam_id``.  If found, issues
    access/refresh tokens and redirects to the OAuth callback page.
    Otherwise creates a new account + User record and does the same,
    leaving ToS/age/entertainment consent unset so the client's ToS
    interstitial (the same one Google OAuth new accounts go through)
    collects and records real consent before the account can be used.
    """
    from airunner_services.database.session import (
        public_session_scope,
    )
    from extensions.auth.server.models import Account

    is_new_account = False

    with public_session_scope() as session:
        existing = session.query(Account).filter(
            Account.steam_id == steam_id,
        ).first()
        if existing is not None:
            account_id = existing.id
            # Reactivate a soft-deleted account and reset the
            # setup-complete flag so the onboarding wizard is
            # shown again (the admin "delete" is a soft-delete
            # that does not clean tenant data).
            if existing.deleted:
                existing.deleted = False
                session.flush()
                from airunner_services.database.session import (
                    session_scope as _t_session,
                )
                from airunner_services.data.tenant import (
                    set_tenant_key as _set_tenant,
                    reset_tenant_key as _reset_tenant,
                    tenant_key_from_schema as _schema_to_key,
                )
                tenant_key = _schema_to_key(existing.tenant_schema)
                token = _set_tenant(tenant_key)
                try:
                    with _t_session() as tsession:
                        from airunner_services.database.models.user import User
                        tsession.query(User).filter(
                            User.id == account_id,
                        ).update(
                            {"setup_complete": False},
                            synchronize_session=False,
                        )
                        tsession.commit()
                finally:
                    _reset_tenant(token)
        else:
            # New account via Steam
            is_new_account = True
            from airunner_services.database.session import (
                session_scope as _t_session,
            )
            from airunner_services.data.tenant import (
                set_tenant_key as _set_tenant,
                reset_tenant_key as _reset_tenant,
                tenant_key_from_schema as _schema_to_key,
            )

            # Create account in public schema. tos_agreed/age_confirmed/
            # entertainment_confirmed are left unset (matching the Google
            # OAuth new-account path) — the client's ToS interstitial
            # collects and records real consent after this redirect.
            account = Account(
                email="",
                username=f"user_{uuid.uuid4().hex[:8]}",
                auth_provider="steam",
                steam_id=steam_id,
                tenant_schema=f"tenant_{uuid.uuid4().hex}",
                is_verified=False,
            )
            session.add(account)
            session.flush()
            account_id = account.id
            tenant_schema = account.tenant_schema

            # Create User record in the tenant schema
            from airunner_services.database.models.user import User
            from ._webapi import (
                get_player_summaries,
                get_steam_level,
            )

            # Fetch Steam profile data
            player = await get_player_summaries(steam_id)
            display_name = (
                player.get("personaname") if player else f"steam_{steam_id[-8:]}"
            )
            avatar_url = player.get("avatarfull", "") if player else ""

            tenant_key = _schema_to_key(tenant_schema)
            token = _set_tenant(tenant_key)
            try:
                with _t_session() as tsession:
                    user = User(
                        id=account_id,
                        username=account.username,
                        display_name=display_name,
                        avatar_image=avatar_url,
                    )
                    tsession.add(user)
                    tsession.commit()

                    # Create a SteamConnection row so the
                    # Integrations panel shows "connected"
                    # immediately after sign-up.
                    conn = SteamConnection(
                        account_id=account_id,
                        steam_id=steam_id,
                        display_name=display_name,
                        avatar_url=avatar_url,
                    )
                    tsession.add(conn)
                    tsession.commit()
            finally:
                _reset_tenant(token)

        # Issue a short-lived one-time handoff code (NOT the real
        # tokens), matching the Google OAuth flow.  Long-lived
        # credentials must never appear in URLs, logs, or browser
        # history.  The frontend immediately exchanges this code via
        # POST /oauth/exchange for real access/refresh tokens.
        from extensions.auth.server.jwt import (
            create_oauth_handoff_token,
        )

        handoff_code = create_oauth_handoff_token(account_id)
        new_param = "&new=1" if is_new_account else ""
        return RedirectResponse(
            url=f"{site_url}/oauth/callback?code={handoff_code}{new_param}",
            status_code=302,
        )


async def _handle_link_mode(
    steam_id: str,
    account_id: int,
    settings_url: str,
) -> RedirectResponse:
    """Link a Steam account to an existing authenticated user."""
    from airunner_services.database.session import (
        public_session_scope,
    )
    from extensions.auth.server.models import Account

    if account_id <= 0:
        return RedirectResponse(
            url=f"{settings_url}&steam_error=invalid_state",
            status_code=302,
        )

    # Look up the user's tenant schema.
    tenant_schema: str | None = None
    try:
        with public_session_scope() as psession:
            acct = psession.query(Account).filter(
                Account.id == account_id,
            ).first()
            if acct:
                tenant_schema = acct.tenant_schema
    except Exception as exc:
        logger.warning("Tenant lookup failed: %s", exc)

    # Activate the tenant context for the DB write.
    tenant_token = None
    if tenant_schema:
        from airunner_services.data.tenant import (
            set_tenant_key,
            tenant_key_from_schema,
        )
        tenant_key = tenant_key_from_schema(tenant_schema)
        if tenant_key:
            tenant_token = set_tenant_key(tenant_key)

    try:
        with session_scope() as session:
            existing = session.query(SteamConnection).filter(
                SteamConnection.account_id == account_id,
            ).first()
            if existing:
                existing.steam_id = steam_id
                existing.error = None
            else:
                conn = SteamConnection(
                    account_id=account_id,
                    steam_id=steam_id,
                )
                session.add(conn)
            session.commit()
    except Exception as exc:
        logger.warning("Failed to store Steam connection: %s", exc)
        return RedirectResponse(
            url=f"{settings_url}&steam_error=connect_failed",
            status_code=302,
        )
    finally:
        if tenant_token is not None:
            from airunner_services.data.tenant import (
                reset_tenant_key,
            )
            reset_tenant_key(tenant_token)

    # Also set steam_id on the Account record (public schema) so
    # _handle_auth_mode can find it for future Steam sign-ins.
    with public_session_scope() as psession:
        acct = psession.query(Account).filter(
            Account.id == account_id,
        ).first()
        if acct is not None:
            acct.steam_id = steam_id
            psession.commit()

    # Fetch Steam profile data immediately so the user sees their
    # profile populated right after linking.
    from ._webapi import (
        get_friend_list,
        get_owned_games,
        get_player_summaries,
        get_recently_played_games,
        get_steam_level,
    )

    import json as _json

    player = await get_player_summaries(steam_id)
    level = await get_steam_level(steam_id)
    games_data = await get_owned_games(steam_id)
    friend_count = await get_friend_list(steam_id)
    recent = await get_recently_played_games(steam_id)

    if player is not None and tenant_schema:
        # Re-establish tenant context (was reset in the finally block
        # above).  SteamConnection lives in the tenant schema.
        fetch_token = None
        try:
            fetch_token = set_tenant_key(tenant_key)
            with session_scope() as session:
                conn = session.query(SteamConnection).filter(
                    SteamConnection.account_id == account_id,
                ).first()
                if conn is not None:
                    conn.display_name = player.get("personaname")
                    conn.avatar_url = player.get("avatarfull")
                    conn.profile_url = player.get("profileurl")
                    conn.persona_state = player.get("personastate")
                    last_logoff = player.get("lastlogoff")
                    if last_logoff:
                        conn.last_logoff = datetime.datetime.utcfromtimestamp(
                            last_logoff,
                        )
                    time_created = player.get("timecreated")
                    if time_created:
                        conn.time_created = datetime.datetime.utcfromtimestamp(
                            time_created,
                        )
                    conn.steam_level = level
                    if games_data is not None:
                        conn.total_games_owned = games_data[
                            "game_count"
                        ]
                        conn.total_playtime_minutes = games_data[
                            "total_playtime_minutes"
                        ]
                        top = games_data.get("top_games", [])
                        if top:
                            conn.top_games_json = _json.dumps(top)
                        all_g = games_data.get("all_games", [])
                        if all_g:
                            conn.all_games_json = _json.dumps(all_g)
                    if recent is not None:
                        conn.recently_played_json = _json.dumps(recent)
                    conn.friend_count = friend_count
                    conn.last_scraped_at = datetime.datetime.utcnow()
                    session.commit()
                    logger.info(
                        "Steam profile data stored for account_id=%s",
                        account_id,
                    )
        except Exception as exc:
            logger.warning(
                "Failed to store Steam profile data: %s", exc,
            )
        finally:
            if fetch_token is not None:
                reset_tenant_key(fetch_token)

    return RedirectResponse(
        url=f"{settings_url}&steam_connected=1", status_code=302,
    )


def _connection_to_dict(conn: SteamConnection) -> dict[str, Any]:
    """Convert a SteamConnection ORM instance to the API response shape."""
    import json as _json

    def _parse_json(val: str | None) -> list | None:
        if not val:
            return None
        try:
            return _json.loads(val)
        except (ValueError, TypeError):
            return None

    return {
        "connected": True,
        "status": conn.status,
        "steam_id": conn.steam_id,
        "display_name": conn.display_name,
        "avatar_url": conn.avatar_url,
        "profile_url": conn.profile_url,
        "persona_state": conn.persona_state,
        "last_logoff": (
            conn.last_logoff.isoformat()
            if conn.last_logoff
            else None
        ),
        "time_created": (
            conn.time_created.isoformat()
            if conn.time_created
            else None
        ),
        "steam_level": conn.steam_level,
        "total_games_owned": conn.total_games_owned,
        "total_playtime_minutes": conn.total_playtime_minutes,
        "friend_count": conn.friend_count,
        "owned_games": _parse_json(conn.top_games_json) or [],
        "all_games": _parse_json(conn.all_games_json) or [],
        "recently_played": _parse_json(conn.recently_played_json) or [],
        "last_scraped_at": (
            conn.last_scraped_at.isoformat()
            if conn.last_scraped_at
            else None
        ),
        "error": conn.error,
    }


# ---- Import Profile -------------------------------------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/import-profile")
async def steam_import_profile(
    account_id: int = Depends(require_auth),
) -> dict[str, Any]:
    """Import Steam profile data into the user's profile.

    Requires ``STEAM_API_KEY``.  Fetches ``GetPlayerSummaries`` for the
    linked Steam account and updates the ``User`` record's
    ``display_name`` and ``avatar_image``.
    """
    from airunner_services.database.models.user import User
    from airunner_services.data.tenant import (
        set_tenant_key as _set_tenant,
        reset_tenant_key as _reset_tenant,
        tenant_key_from_schema as _schema_to_key,
    )
    from airunner_services.database.session import (
        public_session_scope,
    )
    from ._webapi import get_player_summaries

    # Find the linked Steam account
    tenant_token = None
    try:
        with public_session_scope() as psession:
            from extensions.auth.server.models import (
                Account,
            )
            acct = psession.query(Account).filter(
                Account.id == account_id,
            ).first()
            if not acct:
                raise HTTPException(status_code=404, detail="Account not found")
            tenant_schema = str(acct.tenant_schema)

        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == account_id,
            ).first()
            if conn is None:
                raise HTTPException(
                    status_code=404,
                    detail="No Steam account connected",
                )

            # Fetch Steam profile
            player = await get_player_summaries(conn.steam_id)
            if player is None:
                raise HTTPException(
                    status_code=503,
                    detail="Steam API unavailable — set STEAM_API_KEY",
                )

            display_name = player.get("personaname", "")
            avatar_url = player.get("avatarfull", "")

            # Update User record
            user = session.query(User).filter(
                User.id == account_id,
            ).first()
            if user:
                user.display_name = display_name
                user.avatar_image = avatar_url
                session.commit()

            return {
                "display_name": display_name,
                "avatar_url": avatar_url,
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Steam import-profile failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to import Steam profile",
        ) from exc


# ---- OpenID Auth Routes --------------------------------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/auth/login")
async def steam_auth_login(
    request: Request,
    mode: str = Query("link"),
) -> dict[str, Any]:
    """Return the Steam OpenID login URL with a signed state JWT.

    *mode*:
      ``"link"`` — link Steam to the authenticated account (default).
      ``"auth"`` — sign in / sign up with Steam (no auth needed).

    """
    if not _STATE_SECRET:
        raise HTTPException(
            status_code=503,
            detail=(
                "Steam integration is not configured. "
                "Set STEAM_STATE_JWT_SECRET to enable."
            ),
        )

    if mode == "auth":
        # No authentication required — use placeholder account_id 0.
        # The real account will be created in the auth-mode callback.
        account_id = 0
    else:
        # Link mode — require authentication.
        account_id = await require_auth(request)

    state = _steam_state_jwt(account_id, mode=mode)
    if state is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate state token.",
        )

    callback_url = f"{_INSTANCE_URL}/api/v1/steam/auth/callback"
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": f"{callback_url}?state={state}",
        "openid.realm": _INSTANCE_URL,
        "openid.identity": (
            "http://specs.openid.net/auth/2.0/identifier_select"
        ),
        "openid.claimed_id": (
            "http://specs.openid.net/auth/2.0/identifier_select"
        ),
    }
    return {"url": f"{_STEAM_OPENID_URL}?{urlencode(params)}"}


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/auth/callback")
async def steam_auth_callback(
    request: Request,
    state: str = Query(...),
) -> RedirectResponse:
    """Receive OpenID response, validate, extract Steam64 ID.

    Behaviour depends on the *mode* stored in the state JWT:

    * ``"link"`` — link Steam to an already-authenticated account.
    * ``"auth"`` — sign in (existing account) or sign up (new account).
    """
    site_url = _INSTANCE_URL
    settings_url = f"{site_url}/settings?tab=integrations"
    login_url = f"{site_url}/login"

    jwt_account_id, jwt_mode = _decode_state_jwt(state)
    if jwt_account_id is None and jwt_mode == "link":
        logger.warning("Invalid or expired Steam state JWT")
        return RedirectResponse(
            url=f"{settings_url}&steam_error=invalid_state",
            status_code=302,
        )

    query_params = dict(request.query_params)
    query_params.pop("state", None)

    openid_mode = query_params.get("openid.mode", "")
    if openid_mode != "id_res":
        logger.warning("Steam OpenID returned mode=%s", openid_mode)
        redir = (
            f"{login_url}?error=steam_auth_failed"
            if jwt_mode == "auth"
            else f"{settings_url}&steam_error=auth_failed"
        )
        return RedirectResponse(url=redir, status_code=302)

    if _SKIP_VALIDATION:
        valid = True
        logger.info(
            "Skipping OpenID validation "
            "(AIRUNNER_ALLOW_STEAM_SKIP_VALIDATION=1, "
            "deployment_mode=%s)",
            _DEPLOYMENT_MODE,
        )
    else:
        valid = await validate_openid(dict(query_params))
    if not valid:
        logger.warning("Steam OpenID back-channel validation failed")
        redir = (
            f"{login_url}?error=steam_auth_failed"
            if jwt_mode == "auth"
            else f"{settings_url}&steam_error=validation_failed"
        )
        return RedirectResponse(url=redir, status_code=302)

    claimed_id = query_params.get("openid.claimed_id", "")
    steam_id = extract_steam_id(claimed_id)
    if steam_id is None:
        logger.warning(
            "Could not extract Steam ID from claimed_id=%s", claimed_id,
        )
        redir = (
            f"{login_url}?error=steam_auth_failed"
            if jwt_mode == "auth"
            else f"{settings_url}&steam_error=no_steam_id"
        )
        return RedirectResponse(url=redir, status_code=302)

    # ---- Auth mode: sign in / sign up ---- -----------------------------
    if jwt_mode == "auth":
        return await _handle_auth_mode(
            steam_id, site_url, login_url, settings_url,
        )

    # ---- Link mode: attach Steam to existing account ---- ---------------
    return await _handle_link_mode(
        steam_id, jwt_account_id or 0, settings_url,
    )


# ---- RPC Handlers --------------------------------------------------------


@_rpc_register("GET", "/api/v1/steam/auth/login")
async def _rpc_steam_auth_login(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """RPC handler for ``GET /api/v1/steam/auth/login``.

    Mirrors the HTTP endpoint but runs inside the WebSocket RPC
    dispatch so the client can call it without a separate HTTP
    round-trip.
    """
    ws = kw.get("ws")
    if ws is None:
        return {"status": 400, "body": {"error": "WebSocket required"}}

    _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return {
            "status": 401,
            "body": {"error": "Authentication required"},
        }

    if not _STATE_SECRET:
        return {
            "status": 503,
            "body": {
                "error": (
                    "Steam integration is not configured. "
                    "Set STEAM_STATE_JWT_SECRET to enable."
                ),
            },
        }

    state = _steam_state_jwt(account_id)
    if state is None:
        return {
            "status": 500,
            "body": {"error": "Failed to generate state token."},
        }

    from urllib.parse import urlencode as _urlencode

    callback_url = f"{_INSTANCE_URL}/api/v1/steam/auth/callback"
    params = {
        "openid.ns": "http://specs.openid.net/auth/2.0",
        "openid.mode": "checkid_setup",
        "openid.return_to": f"{callback_url}?state={state}",
        "openid.realm": _INSTANCE_URL,
        "openid.identity": (
            "http://specs.openid.net/auth/2.0/identifier_select"
        ),
        "openid.claimed_id": (
            "http://specs.openid.net/auth/2.0/identifier_select"
        ),
    }
    return {
        "status": 200,
        "body": {"url": f"{_STEAM_OPENID_URL}?{_urlencode(params)}"},
    }


# ---- HTTP Status / Profile / Disconnect Routes ---------------------------

# These mirror the RPC handlers so the frontend can call them via HTTP fetch
# (which goes through the Vite proxy to the FastAPI backend).


def _get_auth_provider(user_id: int) -> str | None:
    """Return the auth_provider from the Account record."""
    try:
        from airunner_services.database.session import (
            public_session_scope,
        )
        from extensions.auth.server.models import Account
        with public_session_scope() as psession:
            acct = psession.query(Account).filter(
                Account.id == user_id,
            ).first()
            if acct is not None:
                return acct.auth_provider
    except Exception:
        pass
    return None


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/status/{user_id}")
async def steam_status_http(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """HTTP GET handler for Steam connection status."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == user_id,
            ).first()
            if conn is None:
                logger.info(
                    "Steam status HTTP: no connection for account_id=%s",
                    user_id,
                )
                return {
                    "connected": False,
                    "status": "not_connected",
                    "steam_id": None,
                    "display_name": None,
                    "avatar_url": None,
                    "last_scraped_at": None,
                    "error": None,
                    "auth_provider": _get_auth_provider(user_id),
                }
            return {
                **_connection_to_dict(conn),
                "auth_provider": _get_auth_provider(user_id),
            }
    except Exception as exc:
        logger.warning("Steam status HTTP query failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to query Steam connection status",
        ) from exc


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/profile/{user_id}")
async def steam_profile_http(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """HTTP GET handler for Steam profile info."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == user_id,
            ).first()
            if conn is None:
                raise HTTPException(
                    status_code=404,
                    detail="No Steam account connected",
                )
            return _connection_to_dict(conn)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Steam profile HTTP query failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to query Steam profile",
        ) from exc


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/disconnect/{user_id}")
async def steam_disconnect_http(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """HTTP POST handler for disconnecting Steam."""
    from airunner_services.database.session import (
        public_session_scope,
    )
    from extensions.auth.server.models import Account

    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == user_id,
            ).first()
            if conn is None:
                raise HTTPException(
                    status_code=404,
                    detail="No Steam account connected",
                )
            session.delete(conn)
            session.commit()

        # Clear steam_id on the Account record so future Steam login
        # creates a new account instead of re-linking to this one.
        # Don't clear for steam-only accounts or they'd lose login.
        with public_session_scope() as psession:
            acct = psession.query(Account).filter(
                Account.id == user_id,
            ).first()
            if acct is not None and acct.auth_provider != "steam":
                acct.steam_id = None
                psession.commit()

        return {"message": "Steam account disconnected"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Steam disconnect HTTP failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to disconnect Steam account",
        ) from exc


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/rescrape/{user_id}")
async def steam_rescrape_http(
    request: Request,
    user_id: int,
) -> dict[str, Any]:
    """HTTP POST handler for rescrape (no-op without FastSearch)."""
    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == user_id,
            ).first()
            if conn is None:
                raise HTTPException(
                    status_code=404,
                    detail="No Steam account connected",
                )
            return _connection_to_dict(conn)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Steam rescrape HTTP query failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to query Steam connection",
        ) from exc


# ---- RPC Handlers --------------------------------------------------------


@_rpc_register("GET", "/api/v1/steam/status/{user_id}")
async def _rpc_steam_status(body: dict, **kw: Any) -> dict[str, Any]:
    """Return Steam connection status from the local database."""
    from ._proxy import require_ws_auth

    _ws, aid, err = require_ws_auth(kw)
    if err:
        return err

    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 200,
                    "body": {
                        "connected": False,
                        "status": "not_connected",
                        "steam_id": None,
                        "display_name": None,
                        "avatar_url": None,
                        "last_scraped_at": None,
                        "error": None,
                        "auth_provider": _get_auth_provider(aid),
                    },
                }
            return {
                "status": 200,
                "body": {
                    **_connection_to_dict(conn),
                    "auth_provider": _get_auth_provider(aid),
                },
            }
    except Exception as exc:
        logger.warning("Steam status query failed: %s", exc)
        return {
            "status": 500,
            "body": {"error": "Failed to query Steam connection status"},
        }


@_rpc_register("GET", "/api/v1/steam/profile/{user_id}")
async def _rpc_steam_profile(body: dict, **kw: Any) -> dict[str, Any]:
    """Return Steam connection info (profile scraping requires FastSearch)."""
    from ._proxy import require_ws_auth

    _ws, aid, err = require_ws_auth(kw)
    if err:
        return err

    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 404,
                    "body": {"error": "No Steam account connected"},
                }
            return {"status": 200, "body": _connection_to_dict(conn)}
    except Exception as exc:
        logger.warning("Steam profile query failed: %s", exc)
        return {
            "status": 500,
            "body": {"error": "Failed to query Steam profile"},
        }


@_rpc_register("POST", "/api/v1/steam/disconnect/{user_id}")
async def _rpc_steam_disconnect(body: dict, **kw: Any) -> dict[str, Any]:
    """Remove the Steam connection from the local database."""
    from ._proxy import require_self, require_ws_auth

    _ws, aid, err = require_ws_auth(kw)
    if err:
        return err
    path_params = kw.get("path_params", {})
    err2 = require_self(aid, path_params, "user_id")
    if err2:
        return err2

    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 404,
                    "body": {"error": "No Steam account connected"},
                }
            session.delete(conn)
            session.commit()

        # Clear steam_id on the Account record so future Steam login
        # creates a new account instead of re-linking to this one.
        # Don't clear for steam-only accounts or they'd lose login.
        from airunner_services.database.session import (
            public_session_scope,
        )
        from extensions.auth.server.models import Account

        with public_session_scope() as psession:
            acct = psession.query(Account).filter(
                Account.id == aid,
            ).first()
            if acct is not None and acct.auth_provider != "steam":
                acct.steam_id = None
                psession.commit()

        return {
            "status": 200,
            "body": {"message": "Steam account disconnected"},
        }
    except Exception as exc:
        logger.warning("Steam disconnect failed: %s", exc)
        return {
            "status": 500,
            "body": {"error": "Failed to disconnect Steam account"},
        }


@_rpc_register("POST", "/api/v1/steam/rescrape/{user_id}")
async def _rpc_steam_rescrape(body: dict, **kw: Any) -> dict[str, Any]:
    """Rescrape is a no-op without FastSearch — returns current status."""
    from ._proxy import require_self, require_ws_auth

    _ws, aid, err = require_ws_auth(kw)
    if err:
        return err
    path_params = kw.get("path_params", {})
    err2 = require_self(aid, path_params, "user_id")
    if err2:
        return err2

    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 404,
                    "body": {"error": "No Steam account connected"},
                }
            return {"status": 200, "body": _connection_to_dict(conn)}
    except Exception as exc:
        logger.warning("Steam rescrape query failed: %s", exc)
        return {
            "status": 500,
            "body": {"error": "Failed to query Steam connection"},
        }


# ---- Achievements ---------------------------------------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.get("/achievements/{user_id}")
async def steam_achievements_http(
    request: Request,
    user_id: int,
    appid: int = Query(...),
) -> dict[str, Any]:
    """HTTP GET handler for Steam achievements (cache-aware)."""
    from ._webapi import get_player_achievements

    account_id = await require_auth(request)
    if account_id != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == user_id,
            ).first()
            if conn is None:
                raise HTTPException(
                    status_code=404,
                    detail="No Steam account connected",
                )

            # Check cache first
            cached = _get_cached_achievements(conn, appid)
            if cached is not None:
                return cached

            result = await get_player_achievements(
                conn.steam_id, appid,
            )
            if "error" not in result:
                _cache_achievements(conn, appid, result, session)
            return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "Steam achievements HTTP query failed: %s", exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to query Steam achievements",
        ) from exc


@_rpc_register("GET", "/api/v1/steam/achievements/{user_id}")
async def _rpc_steam_achievements(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """RPC handler for Steam achievements (cache-aware)."""
    from ._proxy import require_ws_auth
    from ._webapi import get_player_achievements

    _ws, aid, err = require_ws_auth(kw)
    if err:
        return err

    appid_str = str(body.get("appid", "0"))
    try:
        appid = int(appid_str)
    except (ValueError, TypeError):
        return {
            "status": 400,
            "body": {"error": "appid query parameter required"},
        }

    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 404,
                    "body": {"error": "No Steam account connected"},
                }

            # Check cache first
            cached = _get_cached_achievements(conn, appid)
            if cached is not None:
                return {"status": 200, "body": cached}

            result = await get_player_achievements(
                conn.steam_id, appid,
            )
            if "error" not in result:
                _cache_achievements(conn, appid, result, session)
            return {"status": 200, "body": result}
    except Exception as exc:
        logger.warning(
            "Steam achievements RPC query failed: %s", exc,
        )
        return {
            "status": 500,
            "body": {"error": "Failed to query Steam achievements"},
        }


# ---- Refresh --------------------------------------------------------------


# nosemgrep: missing-auth-dependency (uses request.state.account_id)
@router.post("/refresh")
async def steam_refresh_http(
    request: Request,
    account_id: int = Depends(require_auth),
) -> dict[str, Any]:
    """Refresh Steam profile data if stale (>4h since last fetch)."""
    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == account_id,
            ).first()
            if conn is None:
                return {"refreshed": False, "status": "not_connected"}
            if not _is_stale(conn):
                return {
                    "refreshed": False,
                    "status": "fresh",
                    "last_scraped_at": (
                        conn.last_scraped_at.isoformat()
                        if conn.last_scraped_at
                        else None
                    ),
                }
            await _refresh_steam_profile(
                conn.steam_id, conn, session,
            )
            return {"refreshed": True, "status": "connected"}
    except Exception as exc:
        logger.warning("Steam refresh HTTP failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh Steam data",
        ) from exc


@_rpc_register("POST", "/api/v1/steam/refresh")
async def _rpc_steam_refresh(
    body: dict, **kw: Any,
) -> dict[str, Any]:
    """RPC handler for Steam data refresh."""
    from ._proxy import require_ws_auth

    _ws, aid, err = require_ws_auth(kw)
    if err:
        return err

    try:
        with session_scope() as session:
            conn = session.query(SteamConnection).filter(
                SteamConnection.account_id == aid,
            ).first()
            if conn is None:
                return {
                    "status": 200,
                    "body": {"refreshed": False,
                     "status": "not_connected"},
                }
            if not _is_stale(conn):
                return {
                    "status": 200,
                    "body": {
                        "refreshed": False,
                        "status": "fresh",
                        "last_scraped_at": (
                            conn.last_scraped_at.isoformat()
                            if conn.last_scraped_at
                            else None
                        ),
                    },
                }
            await _refresh_steam_profile(
                conn.steam_id, conn, session,
            )
            return {
                "status": 200,
                "body": {"refreshed": True,
                 "status": "connected"},
            }
    except Exception as exc:
        logger.warning(
            "Steam refresh RPC failed: %s", exc,
        )
        return {
            "status": 500,
            "body": {"error": "Failed to refresh Steam data"},
        }
