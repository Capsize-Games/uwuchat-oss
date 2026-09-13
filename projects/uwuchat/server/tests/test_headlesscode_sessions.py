"""Route tests for the headlesscode session endpoints.

Covers session detail (header + durable event transcript), account
scoping (cross-account sessions are a 404, not a leak), and the
mid-session message-injection forward (400 blank, 404 foreign, 502
dashboard failure, 200 success) — against the real tenant schema the
auth middleware provisions on first authenticated use.
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
from projects.uwuchat.server.models.headlesscode_session import (
    HeadlesscodeSession,
)
from projects.uwuchat.server.models.headlesscode_session_event import (
    HeadlesscodeSessionEvent,
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
            email=f"hc-sess-{uuid.uuid4().hex[:8]}@example.com",
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


def _seed_project(account: _TestAccount) -> int:
    """Insert a project row in the account's tenant schema."""
    key = tenant_key_from_schema(account.tenant_schema)
    with tenant_scope(key), session_scope() as session:
        row = HeadlesscodeProject(
            user_id=account.id,
            name="acme-web",
            repo_path="/srv/acme",
            workspace_root="/srv/acme",
        )
        session.add(row)
        session.flush()
        return int(row.id)


def _seed_session(
    account: _TestAccount, project_id: int,
    hc_id: str = "hc-sess-1",
) -> int:
    """Insert a session row in the account's tenant schema."""
    key = tenant_key_from_schema(account.tenant_schema)
    with tenant_scope(key), session_scope() as session:
        row = HeadlesscodeSession(
            project_id=project_id,
            headlesscode_session_id=hc_id,
            status="running",
            task_description="fix the login bug",
            mode="code",
        )
        session.add(row)
        session.flush()
        return int(row.id)


def test_session_endpoints_require_auth(_db: str) -> None:
    """No token -> 401 on session detail and injection."""
    c = _client()
    assert c.get(f"{PREFIX}/sessions/x").status_code == 401
    assert c.post(
        f"{PREFIX}/sessions/x/message", json={"text": "hi"},
    ).status_code == 401


def test_session_detail_returns_transcript(_db: str) -> None:
    """Session detail returns the header plus event rows."""
    acct = _make_account()
    project_id = _seed_project(acct)
    session_row_id = _seed_session(acct, project_id, "hc-sess-detail")
    key = tenant_key_from_schema(acct.tenant_schema)
    with tenant_scope(key), session_scope() as session:
        session.add(HeadlesscodeSessionEvent(
            session_id=session_row_id,
            raw_event={"type": "turn", "text": "hello"},
            chat_block_kind="turn",
        ))
        session.commit()

    resp = _client().get(
        f"{PREFIX}/sessions/hc-sess-detail", headers=_headers(acct),
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["session"]["project_name"] == "acme-web"
    assert payload["session"]["status"] == "running"
    assert payload["events"][0]["raw_event"]["type"] == "turn"


def test_session_is_account_scoped(_db: str) -> None:
    """Another account sees the same 404 for a foreign session."""
    owner = _make_account()
    other = _make_account()
    project_id = _seed_project(owner)
    _seed_session(owner, project_id, "hc-sess-private")

    resp = _client().get(
        f"{PREFIX}/sessions/hc-sess-private", headers=_headers(other),
    )
    assert resp.status_code == 404


def test_inject_message_forwards(
    _db: str, monkeypatch,
) -> None:
    """POST message forwards to headlesscode_client.message_session."""
    acct = _make_account()
    project_id = _seed_project(acct)
    _seed_session(acct, project_id, "hc-sess-inject")
    calls = []

    async def _fake_message_session(session_id, text, repo):
        calls.append((session_id, text, repo))
        return {"sessionId": session_id, "ok": True}

    import projects.uwuchat.server.headlesscode_client as hc

    monkeypatch.setattr(hc, "message_session", _fake_message_session)
    resp = _client().post(
        f"{PREFIX}/sessions/hc-sess-inject/message",
        json={"text": "  keep going  "},
        headers=_headers(acct),
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "session_id": "hc-sess-inject"}
    assert calls == [("hc-sess-inject", "keep going", "/srv/acme")]


def test_inject_message_empty_text_rejected(_db: str) -> None:
    """Blank text -> 400 before any forward."""
    acct = _make_account()
    project_id = _seed_project(acct)
    _seed_session(acct, project_id, "hc-sess-blank")
    resp = _client().post(
        f"{PREFIX}/sessions/hc-sess-blank/message",
        json={"text": "   "},
        headers=_headers(acct),
    )
    assert resp.status_code == 400


def test_inject_message_foreign_session_rejected(_db: str) -> None:
    """Cross-account injection -> 404 (not a forward)."""
    owner = _make_account()
    other = _make_account()
    project_id = _seed_project(owner)
    _seed_session(owner, project_id, "hc-sess-cross")
    resp = _client().post(
        f"{PREFIX}/sessions/hc-sess-cross/message",
        json={"text": "hello"},
        headers=_headers(other),
    )
    assert resp.status_code == 404


def test_inject_message_forward_failure_502(_db: str, monkeypatch) -> None:
    """A dashboard failure surfaces as a sanitized 502."""
    acct = _make_account()
    project_id = _seed_project(acct)
    _seed_session(acct, project_id, "hc-sess-down")

    async def _boom(session_id, text, repo):
        del session_id, text, repo
        raise RuntimeError("dashboard unreachable")

    import projects.uwuchat.server.headlesscode_client as hc

    monkeypatch.setattr(hc, "message_session", _boom)
    resp = _client().post(
        f"{PREFIX}/sessions/hc-sess-down/message",
        json={"text": "hello"},
        headers=_headers(acct),
    )
    assert resp.status_code == 502
