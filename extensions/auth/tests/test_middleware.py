"""Functional tests for the JWT authentication middleware.

These tests exercise the middleware's token extraction, tenant context
setting, and account-status enforcement. They use FastAPI's TestClient
with a minimal app so the full middleware stack runs.
"""

from __future__ import annotations

from airunner_services.data.tenant import get_tenant_key
from airunner_services.database.session import reset_engine
from fastapi import FastAPI
from fastapi.testclient import TestClient

from extensions.auth.server.middleware import register as register_auth


def _minimal_app() -> FastAPI:
    """Build a minimal FastAPI app with auth middleware and a protected
    route."""
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/protected")
    async def protected_route():
        return {"account_id": "present", "tenant": get_tenant_key()}

    register_auth(app)
    return app


# ---------------------------------------------------------------------------
# No auth header → 401
# ---------------------------------------------------------------------------


def test_no_auth_header_rejected(_db: str) -> None:
    """A request with no Authorization header on a protected route gets
    401."""
    reset_engine()
    client = TestClient(_minimal_app())
    response = client.get("/api/v1/protected")
    assert response.status_code == 401
    assert "Missing or invalid Authorization header" in response.text


# ---------------------------------------------------------------------------
# Health endpoint is public (no auth)
# ---------------------------------------------------------------------------


def test_health_endpoint_no_auth(_db: str) -> None:
    """The /health endpoint is public and does not require a token."""
    reset_engine()
    client = TestClient(_minimal_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Invalid token → 401
# ---------------------------------------------------------------------------


def test_invalid_token_rejected(_db: str) -> None:
    """A request with a garbage Bearer token gets 401."""
    reset_engine()
    client = TestClient(_minimal_app())
    response = client.get(
        "/api/v1/protected",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert response.status_code == 401
    assert "Invalid or expired token" in response.text


# ---------------------------------------------------------------------------
# Valid token sets tenant context
# ---------------------------------------------------------------------------


def test_valid_token_attaches_tenant_context(_db: str) -> None:
    """A request with a valid access token sets the tenant context."""
    from extensions.auth.server.jwt import create_access_token

    reset_engine()
    client = TestClient(_minimal_app())
    token = create_access_token(1, "tenant_testscope")
    response = client.get(
        "/api/v1/protected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tenant"] is not None


# ---------------------------------------------------------------------------
# Wrong token type rejected
# ---------------------------------------------------------------------------


def test_refresh_token_rejected_on_protected_route(_db: str) -> None:
    """A refresh token (type != 'access') is rejected on a protected
    route."""
    from extensions.auth.server.jwt import create_refresh_token

    reset_engine()
    client = TestClient(_minimal_app())
    token = create_refresh_token(1)
    response = client.get(
        "/api/v1/protected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
    assert "Invalid or expired token" in response.text


# ---------------------------------------------------------------------------
# Embed endpoint is public (no auth)
# ---------------------------------------------------------------------------


def test_embed_text_endpoint_public(_db: str) -> None:
    """The /api/v1/embed/text endpoint (headlesscode embedding backend)
    must be reachable without a token — the auth middleware must treat it
    as a public path."""
    reset_engine()
    app = FastAPI()

    @app.post("/api/v1/embed/text")
    async def embed_text():
        return {"model": "test", "embeddings": []}

    register_auth(app)
    client = TestClient(app)
    response = client.post("/api/v1/embed/text", json={"texts": ["hello"]})
    # Must reach the route (200), not the auth middleware's 401.
    assert response.status_code == 200
    assert response.json() == {"model": "test", "embeddings": []}


# ---------------------------------------------------------------------------
# Token query parameter (for WebSocket upgrades)
# ---------------------------------------------------------------------------


def test_token_via_query_param(_db: str) -> None:
    """A token passed as ?token=... is accepted (WebSocket upgrade
    path)."""
    from extensions.auth.server.jwt import create_access_token

    reset_engine()
    client = TestClient(_minimal_app())
    token = create_access_token(1, "tenant_qs")
    response = client.get(f"/api/v1/protected?token={token}")
    assert response.status_code == 200
