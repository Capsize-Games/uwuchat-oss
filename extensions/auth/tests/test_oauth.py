"""Tests for OAuth routes — capabilities endpoint and not-configured
redirect behaviour.

Covers the regression that ``google_oauth_not_configured`` and
``twitch_oauth_not_configured`` error codes behave correctly and that
the capabilities endpoint never leaks credential values.
"""

from __future__ import annotations

import importlib
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from extensions.auth.server import oauth as google_oauth_mod
from extensions.auth.server import twitch_oauth as twitch_oauth_mod

_MODULES_TO_RESTORE = (
    "extensions.auth.server.oauth",
    "extensions.auth.server.twitch_oauth",
    "extensions.auth.server.routes",
    "extensions.auth.server.oauth_capabilities_routes",
)


@pytest.fixture(autouse=True)
def _restore_oauth_modules() -> Generator[None, None, None]:
    """Reload OAuth modules back to real-env state after each test.

    Tests that call ``importlib.reload()`` on these modules leave them
    reflecting test-specific env vars.  Without this fixture, any later
    test that imports ``OAUTH_CONFIGURED`` (directly or transitively)
    sees stale state — an order-dependent pollution bug.
    """
    import os as _os

    _orig_google_id = _os.environ.get("AIRUNNER_GOOGLE_CLIENT_ID")
    _orig_google_secret = _os.environ.get("AIRUNNER_GOOGLE_CLIENT_SECRET")
    _orig_twitch_id = _os.environ.get("AIRUNNER_TWITCH_CLIENT_ID")
    _orig_twitch_secret = _os.environ.get("AIRUNNER_TWITCH_CLIENT_SECRET")

    yield  # test runs here — may reload modules with altered env vars

    _restore_env("AIRUNNER_GOOGLE_CLIENT_ID", _orig_google_id)
    _restore_env("AIRUNNER_GOOGLE_CLIENT_SECRET", _orig_google_secret)
    _restore_env("AIRUNNER_TWITCH_CLIENT_ID", _orig_twitch_id)
    _restore_env("AIRUNNER_TWITCH_CLIENT_SECRET", _orig_twitch_secret)

    for _mod_name in _MODULES_TO_RESTORE:
        importlib.reload(importlib.import_module(_mod_name))


def _restore_env(key: str, value: str | None) -> None:
    """Set or delete an env var, matching the original state."""
    import os as _os

    if value is None:
        _os.environ.pop(key, None)
    else:
        _os.environ[key] = value


# ── Google OAuth login redirect when not configured ────────────────


def test_google_login_redirects_with_not_configured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When Google OAuth is not configured, ``GET .../google/login``
    redirects to ``/login?error=google_oauth_not_configured``."""
    monkeypatch.delenv("AIRUNNER_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("AIRUNNER_GOOGLE_CLIENT_SECRET", raising=False)
    importlib.reload(google_oauth_mod)
    importlib.reload(twitch_oauth_mod)
    from extensions.auth.server import routes as auth_routes
    importlib.reload(auth_routes)

    from extensions.auth.server.limiter import limiter

    limiter.enabled = False
    app = FastAPI()
    app.include_router(
        auth_routes.router,
        prefix="/api/v1/auth",
    )
    client = TestClient(app)
    response = client.get(
        "/api/v1/auth/oauth/google/login",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "google_oauth_not_configured" in response.headers["location"]


# ── Twitch OAuth login redirect when not configured ────────────────


def test_twitch_login_redirects_with_not_configured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When Twitch OAuth is not configured, ``GET .../twitch/login``
    redirects to ``/login?error=twitch_oauth_not_configured``."""
    monkeypatch.delenv("AIRUNNER_TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("AIRUNNER_TWITCH_CLIENT_SECRET", raising=False)
    importlib.reload(google_oauth_mod)
    importlib.reload(twitch_oauth_mod)
    from extensions.auth.server import routes as auth_routes
    importlib.reload(auth_routes)

    from extensions.auth.server.limiter import limiter

    limiter.enabled = False
    app = FastAPI()
    # Do NOT register middleware — it may require database connectivity
    # that adds unnecessary test coupling for a simple redirect check.
    app.include_router(
        auth_routes.router,
        prefix="/api/v1/auth",
    )
    client = TestClient(app)
    response = client.get(
        "/api/v1/auth/oauth/twitch/login",
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "twitch_oauth_not_configured" in response.headers["location"]


# ── Capabilities endpoint (via oauth_capabilities_routes) ──────────


def _capabilities_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a minimal app that includes the capabilities router."""
    from extensions.auth.server.limiter import limiter

    monkeypatch.delenv("AIRUNNER_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("AIRUNNER_GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("AIRUNNER_TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("AIRUNNER_TWITCH_CLIENT_SECRET", raising=False)

    importlib.reload(google_oauth_mod)
    importlib.reload(twitch_oauth_mod)
    # Reload capabilities module so it picks up new OAUTH_CONFIGURED.
    from extensions.auth.server import oauth_capabilities_routes
    importlib.reload(oauth_capabilities_routes)

    limiter.enabled = False
    app = FastAPI()
    app.include_router(
        oauth_capabilities_routes.router,
        prefix="/api/v1/auth",
    )
    return TestClient(app)


def test_capabilities_returns_false_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The capabilities endpoint returns ``false`` when no credentials
    are set and never leaks credential values in the response."""
    client = _capabilities_client(monkeypatch)
    response = client.get("/api/v1/auth/oauth/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body == {"google": False, "twitch": False}
    # Audit: ensure no credential keys leaked.
    for key in body:
        assert "client_id" not in key.lower()
        assert "secret" not in key.lower()


def test_capabilities_returns_true_when_google_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The capabilities endpoint returns ``google: true`` when
    Google credentials are set."""
    monkeypatch.setenv("AIRUNNER_GOOGLE_CLIENT_ID", "test-id")
    monkeypatch.setenv("AIRUNNER_GOOGLE_CLIENT_SECRET", "test-secret")
    monkeypatch.delenv("AIRUNNER_TWITCH_CLIENT_ID", raising=False)
    monkeypatch.delenv("AIRUNNER_TWITCH_CLIENT_SECRET", raising=False)

    importlib.reload(google_oauth_mod)
    importlib.reload(twitch_oauth_mod)
    from extensions.auth.server import oauth_capabilities_routes
    importlib.reload(oauth_capabilities_routes)

    from extensions.auth.server.limiter import limiter

    limiter.enabled = False
    app = FastAPI()
    app.include_router(
        oauth_capabilities_routes.router,
        prefix="/api/v1/auth",
    )
    client = TestClient(app)
    response = client.get("/api/v1/auth/oauth/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["google"] is True
    assert body["twitch"] is False


def test_capabilities_returns_true_when_twitch_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The capabilities endpoint returns ``twitch: true`` when
    Twitch credentials are set."""
    monkeypatch.delenv("AIRUNNER_GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.delenv("AIRUNNER_GOOGLE_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("AIRUNNER_TWITCH_CLIENT_ID", "test-id")
    monkeypatch.setenv("AIRUNNER_TWITCH_CLIENT_SECRET", "test-secret")

    importlib.reload(google_oauth_mod)
    importlib.reload(twitch_oauth_mod)
    from extensions.auth.server import oauth_capabilities_routes
    importlib.reload(oauth_capabilities_routes)

    from extensions.auth.server.limiter import limiter

    limiter.enabled = False
    app = FastAPI()
    app.include_router(
        oauth_capabilities_routes.router,
        prefix="/api/v1/auth",
    )
    client = TestClient(app)
    response = client.get("/api/v1/auth/oauth/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["google"] is False
    assert body["twitch"] is True
