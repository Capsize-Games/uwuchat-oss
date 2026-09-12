"""Route tests for the admin-only code-credits endpoints.

Every endpoint must be gated by ``require_superuser`` (401
unauthenticated, 403 non-admin), and money values must round-trip as
strings so JSON cannot surprise on decimal precision.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from airunner_services.contract_enums import ModelService
from airunner_services.database.session import public_session_scope
from extensions.auth.server.jwt import create_access_token
from extensions.auth.server.limiter import limiter
from extensions.auth.server.middleware import register as register_auth
from extensions.auth.server.models import Account
from projects.uwuchat.server.code_credits_routes import router

PREFIX = "/api/v1/uwuchat/code-credits"


@dataclass
class _TestAccount:
    """Lightweight value object to avoid DetachedInstanceError."""

    id: int
    tenant_schema: str


def _make_account(*, superuser: bool = False) -> _TestAccount:
    """Create a test Account with a unique email and return it."""
    with public_session_scope() as session:
        acct = Account(
            email=f"cc-route-{uuid.uuid4().hex[:8]}@example.com",
            username=f"u_{uuid.uuid4().hex[:8]}",
            password_hash="unused",
            tenant_schema=f"tenant_{uuid.uuid4().hex}",
            auth_provider=ModelService.LOCAL.value,
            is_superuser=superuser,
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
    return create_access_token(account.id, account.tenant_schema)


def _client() -> TestClient:
    """A test app with auth middleware and the code-credits router."""
    limiter.enabled = False
    app = FastAPI()
    register_auth(app)
    app.include_router(router, prefix=PREFIX)
    return TestClient(app)


def _auth_headers(account: _TestAccount) -> dict:
    return {"Authorization": f"Bearer {_token(account)}"}


def test_get_balance_requires_auth(_db: str) -> None:
    """No token -> 401."""
    target = _make_account()
    resp = _client().get(f"{PREFIX}/{target.id}")
    assert resp.status_code == 401


def test_get_balance_requires_superuser(_db: str) -> None:
    """Authenticated non-admin -> 403."""
    user = _make_account()
    target = _make_account()
    resp = _client().get(
        f"{PREFIX}/{target.id}", headers=_auth_headers(user)
    )
    assert resp.status_code == 403


def test_get_balance_returns_zero_for_fresh_account(_db: str) -> None:
    """A fresh account has a string balance of 0.0000."""
    admin = _make_account(superuser=True)
    target = _make_account()
    resp = _client().get(
        f"{PREFIX}/{target.id}", headers=_auth_headers(admin)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["balance_usd"] == "0.0000"
    assert body["recent_transactions"] == []


def test_get_balance_unknown_account_is_404(_db: str) -> None:
    """Unknown account -> 404 (quota_routes convention)."""
    admin = _make_account(superuser=True)
    resp = _client().get(
        f"{PREFIX}/999999999", headers=_auth_headers(admin)
    )
    assert resp.status_code == 404


def test_topup_requires_auth(_db: str) -> None:
    """No token -> 401."""
    target = _make_account()
    resp = _client().post(
        f"{PREFIX}/{target.id}/topup",
        json={"amount_usd": "5.00", "note": "x"},
    )
    assert resp.status_code == 401


def test_topup_requires_superuser(_db: str) -> None:
    """Authenticated non-admin -> 403."""
    admin = _make_account(superuser=True)
    user = _make_account()
    resp = _client().post(
        f"{PREFIX}/{user.id}/topup",
        json={"amount_usd": "5.00", "note": "x"},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 403


def test_topup_rejects_non_positive_amounts(_db: str) -> None:
    """Zero and negative top-ups -> 400."""
    admin = _make_account(superuser=True)
    target = _make_account()
    client = _client()
    for bad in ("0", "-5", "0.0000"):
        resp = client.post(
            f"{PREFIX}/{target.id}/topup",
            json={"amount_usd": bad, "note": "bad"},
            headers=_auth_headers(admin),
        )
        assert resp.status_code == 400, (
            f"Expected 400 for amount {bad!r}, "
            f"got {resp.status_code}"
        )


def test_topup_rejects_non_decimal_amount(_db: str) -> None:
    """A non-decimal amount string -> 400."""
    admin = _make_account(superuser=True)
    target = _make_account()
    resp = _client().post(
        f"{PREFIX}/{target.id}/topup",
        json={"amount_usd": "not-a-number", "note": "bad"},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 400


def test_topup_round_trips_into_balance_and_ledger(_db: str) -> None:
    """A valid top-up raises the balance and records a transaction."""
    admin = _make_account(superuser=True)
    target = _make_account()
    client = _client()
    headers = _auth_headers(admin)

    resp = client.post(
        f"{PREFIX}/{target.id}/topup",
        json={"amount_usd": "25.50", "note": "manual top-up"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["balance_usd"] == "25.5000"

    resp = client.get(f"{PREFIX}/{target.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["balance_usd"] == "25.5000"
    assert len(body["recent_transactions"]) == 1
    tx = body["recent_transactions"][0]
    assert tx["amount_usd"] == "25.5000"
    assert tx["kind"] == "topup"
    assert tx["session_id"] is None
    assert tx["note"] == "manual top-up"
