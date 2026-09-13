"""Route tests for the headlesscode project registry endpoints.

Covers the auth gate (401 unauthenticated), project CRUD against the
real tenant schema the auth middleware provisions, duplicate-name
conflicts (409), and blank-field validation (400).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from airunner_services.contract_enums import ModelService
from airunner_services.data.tenant import (
    tenant_key_from_schema,
    tenant_scope,
)
from airunner_services.database.session import (
    public_session_scope,
    session_scope,
)
from extensions.auth.server.jwt import create_access_token
from extensions.auth.server.limiter import limiter
from extensions.auth.server.middleware import register as register_auth
from extensions.auth.server.models import Account
from projects.uwuchat.server.models.headlesscode_project import (
    HeadlesscodeProject,
)
from projects.uwuchat.server.routes.headlesscode_routes import router

PREFIX = "/api/v1/uwuchat/headlesscode"


@dataclass
class _TestAccount:
    """Lightweight value object to avoid DetachedInstanceError."""

    id: int
    tenant_schema: str


def _make_account() -> _TestAccount:
    """Create a test Account (plus its tenant User row) and return it."""
    with public_session_scope() as session:
        acct = Account(
            email=f"hc-route-{uuid.uuid4().hex[:8]}@example.com",
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
    # Registration mirrors the OAuth flow, which seeds a User row in
    # the tenant schema with id == account id; headlesscode_projects
    # and headlesscode_sessions FK to users.id.
    from airunner_services.database.models.user import User

    key = tenant_key_from_schema(result.tenant_schema)
    with tenant_scope(key), session_scope() as session:
        session.add(User(id=result.id, username=f"u_{result.id}"))
        session.commit()
    return result


def _client() -> TestClient:
    """A test app with auth middleware and the headlesscode router."""
    limiter.enabled = False
    app = FastAPI()
    register_auth(app)
    app.include_router(router, prefix=PREFIX)
    return TestClient(app)


def _headers(account: _TestAccount) -> dict:
    """Return Bearer auth headers for *account*."""
    token = create_access_token(account.id, account.tenant_schema)
    return {"Authorization": f"Bearer {token}"}


def _seed_project(
    account: _TestAccount, name: str = "acme-web",
) -> int:
    """Insert a project row in the account's tenant schema."""
    key = tenant_key_from_schema(account.tenant_schema)
    with tenant_scope(key), session_scope() as session:
        row = HeadlesscodeProject(
            user_id=account.id,
            name=name,
            repo_path="/srv/acme",
            workspace_root="/srv/acme",
        )
        session.add(row)
        session.flush()
        return int(row.id)


def test_endpoints_require_auth(_db: str) -> None:
    """No token -> 401 on every project endpoint."""
    c = _client()
    assert c.get(f"{PREFIX}/projects").status_code == 401
    assert c.post(f"{PREFIX}/projects", json={}).status_code == 401
    assert c.patch(f"{PREFIX}/projects/1", json={}).status_code == 401
    assert c.delete(f"{PREFIX}/projects/1").status_code == 401


def test_project_crud_roundtrip(_db: str) -> None:
    """Create → list → update → soft-delete lifecycle works."""
    acct = _make_account()
    c = _client()
    body = {
        "name": "acme-web",
        "repo_path": "/srv/acme",
        "workspace_root": "/srv/acme",
    }
    created = c.post(
        f"{PREFIX}/projects", json=body, headers=_headers(acct),
    )
    assert created.status_code == 201
    project_id = created.json()["id"]

    listed = c.get(f"{PREFIX}/projects", headers=_headers(acct))
    assert listed.status_code == 200
    assert [p["name"] for p in listed.json()["projects"]] == ["acme-web"]

    updated = c.patch(
        f"{PREFIX}/projects/{project_id}",
        json={"name": "acme-web", "repo_path": "/srv/acme2",
              "workspace_root": "/srv/acme2"},
        headers=_headers(acct),
    )
    assert updated.status_code == 200
    assert updated.json()["repo_path"] == "/srv/acme2"

    deleted = c.delete(
        f"{PREFIX}/projects/{project_id}", headers=_headers(acct),
    )
    assert deleted.status_code == 204
    after = c.get(f"{PREFIX}/projects", headers=_headers(acct))
    assert after.json()["projects"] == []


def test_create_project_duplicate_name_conflicts(_db: str) -> None:
    """Duplicate names for one account -> 409."""
    acct = _make_account()
    c = _client()
    _seed_project(acct, name="acme-web")
    resp = c.post(
        f"{PREFIX}/projects",
        json={"name": "acme-web", "repo_path": "/x",
              "workspace_root": "/x"},
        headers=_headers(acct),
    )
    assert resp.status_code == 409


def test_create_project_blank_fields_rejected(_db: str) -> None:
    """Missing/blank fields -> 400."""
    acct = _make_account()
    resp = _client().post(
        f"{PREFIX}/projects",
        json={"name": "   ", "repo_path": "/x", "workspace_root": "/x"},
        headers=_headers(acct),
    )
    assert resp.status_code == 400
