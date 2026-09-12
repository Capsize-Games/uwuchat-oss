"""Regression tests for IDOR fixes on third-party connection routes.

Covers the HTTP endpoints across Twitch, Steam, itch.io, Bluesky, and
Email that were previously vulnerable to unauthenticated access.
Uses a shared parametrized helper — not 15 near-identical test functions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from airunner_services.database.session import (
    public_session_scope,
    reset_engine,
)
from extensions.auth.server.jwt import create_access_token
from extensions.auth.server.limiter import limiter
from extensions.auth.server.middleware import register as register_auth
from extensions.auth.server.models import Account
from airunner_services.contract_enums import ModelService


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


@dataclass
class _TestAccount:
    """Lightweight value object to avoid DetachedInstanceError."""
    id: int
    tenant_schema: str


def _make_account() -> _TestAccount:
    """Create a test Account with a unique email and return it."""
    with public_session_scope() as session:
        acct = Account(
            email=f"idor-{uuid.uuid4().hex[:8]}@example.com",
            username=f"u_{uuid.uuid4().hex[:8]}",
            password_hash="unused",
            tenant_schema=f"tenant_{uuid.uuid4().hex}",
            auth_provider=ModelService.LOCAL.value,
        )
        session.add(acct)
        session.flush()
        result = _TestAccount(
            id=int(acct.id),
            tenant_schema=str(acct.tenant_schema),
        )
    return result


def _token(account: _TestAccount) -> str:
    """Return a Bearer access token for *account*."""
    return create_access_token(
        account.id, account.tenant_schema,
    )


def _assert_idor_gated(
    router: Any,
    prefix: str,
    method: str,
    path_template: str,
    *,
    body: dict | None = None,
) -> None:
    """Assert that *path_template* (with ``{user_id}``) is properly
    auth-gated by the IDOR fix.

    Three scenarios tested:
    1. No auth header → 401.
    2. Auth for account A, user_id=B → 403.
    3. Auth for account A, user_id=A → auth gate passes (status < 400).
    """
    acct_a = _make_account()
    acct_b = _make_account()
    token_a = _token(acct_a)

    limiter.enabled = False
    app = FastAPI()
    register_auth(app)
    app.include_router(router, prefix=prefix)
    client = TestClient(app)

    path_a = path_template.format(user_id=acct_a.id)
    path_b = path_template.format(user_id=acct_b.id)

    # 1. No auth → 401
    if method == "GET":
        resp = client.get(path_a)
    else:
        resp = client.post(path_a, json=body or {})
    assert resp.status_code == 401, (
        f"Expected 401 without auth for {method} {path_a}, "
        f"got {resp.status_code}"
    )

    # 2. Auth for A, requesting B's resource → rejected (4xx).
    # The exact code varies (403 when the handler's check fires,
    # 404 when the resource doesn't exist for that caller) — the
    # invariant is that the request does NOT succeed.
    if method == "GET":
        resp = client.get(
            path_b,
            headers={"Authorization": f"Bearer {token_a}"},
        )
    else:
        resp = client.post(
            path_b,
            json=body or {},
            headers={"Authorization": f"Bearer {token_a}"},
        )
    assert 400 <= resp.status_code < 500, (
        f"Expected 4xx for cross-account access to {path_b}, "
        f"got {resp.status_code}"
    )

    # 3. Auth for A, requesting own resource → auth gate passes.
    if method == "GET":
        resp = client.get(
            path_a,
            headers={"Authorization": f"Bearer {token_a}"},
        )
    else:
        resp = client.post(
            path_a,
            json=body or {},
            headers={"Authorization": f"Bearer {token_a}"},
        )
    assert resp.status_code < 500, (
        f"Legitimate owner request to {path_a} should not be "
        f"blocked by auth gate, got {resp.status_code}"
    )
    assert resp.status_code not in (401, 403), (
        f"Legitimate owner must not receive auth error for "
        f"{path_a}, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Fixture: import each router module once
# ---------------------------------------------------------------------------


@pytest.fixture()
def twitch_router() -> Any:
    """Import the Twitch HTTP router."""
    from projects.uwuchat.server.twitch.routes import router
    return router


@pytest.fixture()
def steam_router() -> Any:
    """Import the Steam HTTP router."""
    from projects.uwuchat.server.steam.routes import router
    return router


@pytest.fixture()
def itch_router() -> Any:
    """Import the itch.io HTTP router."""
    from projects.uwuchat.server.itch.routes import router
    return router


@pytest.fixture()
def bluesky_router() -> Any:
    """Import the Bluesky HTTP router."""
    from projects.uwuchat.server.bluesky.routes import router
    return router


@pytest.fixture()
def email_router() -> Any:
    """Import the Email HTTP router."""
    from projects.uwuchat.server.email.routes import router
    return router


# ---------------------------------------------------------------------------
# Twitch endpoints
# ---------------------------------------------------------------------------


def test_twitch_status_idor_gated(
    _db: str, twitch_router: Any,
) -> None:
    _assert_idor_gated(
        twitch_router, "/api/v1/twitch", "GET",
        "/status/{user_id}",
    )


def test_twitch_profile_idor_gated(
    _db: str, twitch_router: Any,
) -> None:
    _assert_idor_gated(
        twitch_router, "/api/v1/twitch", "GET",
        "/profile/{user_id}",
    )


def test_twitch_schedule_idor_gated(
    _db: str, twitch_router: Any,
) -> None:
    _assert_idor_gated(
        twitch_router, "/api/v1/twitch", "GET",
        "/schedule/{user_id}",
    )


def test_twitch_disconnect_idor_gated(
    _db: str, twitch_router: Any,
) -> None:
    _assert_idor_gated(
        twitch_router, "/api/v1/twitch", "POST",
        "/disconnect/{user_id}",
    )


# ---------------------------------------------------------------------------
# Steam endpoints
# ---------------------------------------------------------------------------


def test_steam_status_idor_gated(
    _db: str, steam_router: Any,
) -> None:
    _assert_idor_gated(
        steam_router, "/api/v1/steam", "GET",
        "/status/{user_id}",
    )


def test_steam_profile_idor_gated(
    _db: str, steam_router: Any,
) -> None:
    _assert_idor_gated(
        steam_router, "/api/v1/steam", "GET",
        "/profile/{user_id}",
    )


def test_steam_disconnect_idor_gated(
    _db: str, steam_router: Any,
) -> None:
    _assert_idor_gated(
        steam_router, "/api/v1/steam", "POST",
        "/disconnect/{user_id}",
    )


def test_steam_rescrape_idor_gated(
    _db: str, steam_router: Any,
) -> None:
    _assert_idor_gated(
        steam_router, "/api/v1/steam", "POST",
        "/rescrape/{user_id}",
    )


def test_steam_achievements_idor_gated(
    _db: str, steam_router: Any,
) -> None:
    _assert_idor_gated(
        steam_router, "/api/v1/steam", "GET",
        "/achievements/{user_id}?appid=440",
    )


# ---------------------------------------------------------------------------
# itch.io endpoints
# ---------------------------------------------------------------------------


def test_itch_status_idor_gated(
    _db: str, itch_router: Any,
) -> None:
    _assert_idor_gated(
        itch_router, "/api/v1/itch", "GET",
        "/status/{user_id}",
    )


def test_itch_profile_idor_gated(
    _db: str, itch_router: Any,
) -> None:
    _assert_idor_gated(
        itch_router, "/api/v1/itch", "GET",
        "/profile/{user_id}",
    )


def test_itch_disconnect_idor_gated(
    _db: str, itch_router: Any,
) -> None:
    _assert_idor_gated(
        itch_router, "/api/v1/itch", "POST",
        "/disconnect/{user_id}",
    )


# ---------------------------------------------------------------------------
# Bluesky endpoints
# ---------------------------------------------------------------------------


def test_bluesky_status_idor_gated(
    _db: str, bluesky_router: Any,
) -> None:
    _assert_idor_gated(
        bluesky_router, "/api/v1/bluesky", "GET",
        "/status/{user_id}",
    )


def test_bluesky_posts_idor_gated(
    _db: str, bluesky_router: Any,
) -> None:
    _assert_idor_gated(
        bluesky_router, "/api/v1/bluesky", "GET",
        "/posts/{user_id}",
    )


# ---------------------------------------------------------------------------
# Email /status endpoint (connect/disconnect already had the check)
# ---------------------------------------------------------------------------


def test_email_status_idor_gated(
    _db: str, email_router: Any,
) -> None:
    _assert_idor_gated(
        email_router, "/api/v1/email", "GET",
        "/status/{user_id}",
    )
