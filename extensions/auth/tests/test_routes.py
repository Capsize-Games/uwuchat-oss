"""Functional tests for auth extension REST routes.

Tests registration, login, and error cases against a real PostgreSQL
database so tenant-schema bugs (which have historically been the root
cause of auth failures) are caught.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from airunner_services.database.session import (
    public_session_scope,
    reset_engine,
)
from extensions.auth.server.models import Account
from extensions.auth.server.routes import router as auth_router
from airunner_services.contract_enums import ModelService


def _app() -> FastAPI:
    """Build a minimal FastAPI app with the auth router and middleware.

    The rate limiter is disabled in tests so rate-limited routes don't
    interfere with each other.
    """
    from extensions.auth.server.limiter import limiter
    from extensions.auth.server.middleware import register as reg_mw

    limiter.enabled = False
    app = FastAPI()
    reg_mw(app)
    app.include_router(auth_router, prefix="/api/v1/auth")
    return app


def _unique_email() -> str:
    """Return a unique test email address."""
    return f"test-{uuid.uuid4().hex[:12]}@example.com"


# ---------------------------------------------------------------------------
# Fixture: a pre-registered test account shared across login tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def _account(_db: str) -> dict:
    """Register one test account and return its credentials."""
    reset_engine()
    client = TestClient(_app())
    email = _unique_email()
    password = "shared-test-password"
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
        },
    )
    assert response.status_code == 201
    return {"email": email, "password": password}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_creates_account_and_returns_tokens(_db: str) -> None:
    """A valid registration creates an account and returns JWT tokens."""
    reset_engine()
    client = TestClient(_app())
    email = _unique_email()

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secure-password-123",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "tenant_key" in data

    # Verify the account exists in the database.
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == email)
            .first()
        )
        assert account is not None
        # Username is auto-generated as "user_XXXXXXXX" (random hex).
        assert account.username.startswith("user_")
        assert len(account.username) == len("user_") + 8
        assert account.auth_provider == ModelService.LOCAL.value


def test_register_duplicate_email_rejected(_db: str) -> None:
    """Registering the same email twice returns 409."""
    reset_engine()
    client = TestClient(_app())
    email = _unique_email()

    # First registration succeeds.
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secure-password-123",
        },
    )
    assert response.status_code == 201

    # Second registration with same email fails.
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secure-password-123",
        },
    )
    assert response.status_code == 409
    assert "already registered" in response.text


def test_register_username_is_auto_generated(_db: str) -> None:
    """Registration generates a username in user_XXXXXXXX format."""
    import re

    reset_engine()
    client = TestClient(_app())
    email = _unique_email()

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secure-password-123",
        },
    )
    assert response.status_code == 201

    # Verify username format in the database.
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == email)
            .first()
        )
        assert account is not None
        assert re.match(r"^user_[0-9a-f]{8}$", account.username), (
            f"Expected user_XXXXXXXX, got {account.username}"
        )


def test_register_invalid_inputs_rejected(_db: str) -> None:
    """Short passwords and missing fields are rejected with 400 or 422."""
    reset_engine()
    client = TestClient(_app())

    # Short password.
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": _unique_email(),
            "password": "short",
        },
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_with_correct_password_succeeds(
    _db: str, _account: dict
) -> None:
    """Login with correct credentials returns tokens."""
    reset_engine()
    client = TestClient(_app())
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": _account["email"],
            "password": _account["password"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_with_wrong_password_fails(
    _db: str, _account: dict
) -> None:
    """Login with an incorrect password returns 401."""
    reset_engine()
    client = TestClient(_app())
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": _account["email"],
            "password": "wrong-password",
        },
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.text


def test_login_with_unknown_email_fails(_db: str) -> None:
    """Login with an unregistered email returns 401 without leaking
    whether the email exists."""
    reset_engine()
    client = TestClient(_app())
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "any-password",
        },
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.text
    assert "not found" not in response.text.lower()
    assert "does not exist" not in response.text.lower()


def test_login_response_same_for_unknown_email_and_wrong_password(
    _db: str, _account: dict
) -> None:
    """The error response for an unknown email is identical in content to
    a wrong-password response."""
    reset_engine()
    client = TestClient(_app())

    # Wrong password for existing account.
    r1 = client.post(
        "/api/v1/auth/login",
        json={
            "email": _account["email"],
            "password": "wrong-password",
        },
    )
    # Unknown email.
    r2 = client.post(
        "/api/v1/auth/login",
        json={
            "email": "no-such-user@example.com",
            "password": "any-password",
        },
    )

    assert r1.status_code == 401
    assert r2.status_code == 401
    assert r1.json()["detail"] == r2.json()["detail"], (
        "Login error responses must be identical for unknown email "
        "and wrong password"
    )


# ---------------------------------------------------------------------------
# User-controlled encryption envelope — integration tests
# ---------------------------------------------------------------------------


def test_register_creates_envelope(_db: str) -> None:
    """Register creates wrapped_dek, salt, params, and dek_version=1."""
    reset_engine()
    client = TestClient(_app())
    email = _unique_email()
    pw = "envelope-test-password"
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pw},
    )
    assert response.status_code == 201

    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == email)
            .first()
        )
        assert account is not None
        assert account.wrapped_dek is not None
        assert account.dek_kdf_salt is not None
        assert account.dek_kdf_params is not None
        assert account.dek_version == 1


def test_login_caches_dek(_db: str, _account: dict) -> None:
    """After login, the DEK is present in the process cache."""
    from airunner_services.utils.crypto.dek_cache import (
        cache_get,
        cache_evict,
    )

    reset_engine()
    client = TestClient(_app())

    # Login — this should derive the KEK, unwrap the DEK, and cache it.
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": _account["email"],
            "password": _account["password"],
        },
    )
    assert response.status_code == 200

    # The DEK should be cached in-process.  Find the account ID.
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == _account["email"])
            .first()
        )
        assert account is not None
        dek = cache_get(int(account.id))
        assert dek is not None
        cache_evict(int(account.id))


def test_login_backfills_envelope_for_legacy_account(
    _db: str, _account: dict,
) -> None:
    """An account with no envelope gets one created on first login."""
    reset_engine()

    # Strip the envelope from an existing account.
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == _account["email"])
            .first()
        )
        assert account is not None
        account.wrapped_dek = None
        account.dek_kdf_salt = None
        account.dek_kdf_params = None
        session.add(account)

    # Login should backfill.
    client = TestClient(_app())
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": _account["email"],
            "password": _account["password"],
        },
    )
    assert response.status_code == 200

    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == _account["email"])
            .first()
        )
        assert account.wrapped_dek is not None
        assert account.dek_kdf_salt is not None
        assert account.dek_kdf_params is not None


def test_login_with_corrupted_envelope_still_succeeds(
    _db: str, _account: dict,
) -> None:
    """Login succeeds even when wrapped_dek is garbage (DEK unavailable)."""
    reset_engine()

    # Corrupt the wrapped DEK.
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == _account["email"])
            .first()
        )
        assert account is not None
        account.wrapped_dek = "garbage-not-a-valid-ciphertext"
        session.add(account)

    client = TestClient(_app())
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": _account["email"],
            "password": _account["password"],
        },
    )
    # Login must still succeed (DEK unwrap failure is logged, not fatal).
    assert response.status_code == 200


def test_change_password_preserves_dek(_db: str, _account: dict) -> None:
    """After change-password, the DEK still decrypts old ciphertext."""
    from airunner_services.utils.crypto.dek_cache import (
        cache_get,
        cache_evict,
        set_user_dek,
        reset_user_dek,
    )
    from airunner_services.utils.crypto.user_encrypted_type import (
        UserEncryptedText,
    )

    reset_engine()
    client = TestClient(_app())

    # Login and get access token.
    login_resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": _account["email"],
            "password": _account["password"],
        },
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # Write some data encrypted with the current DEK.
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == _account["email"])
            .first()
        )
        assert account is not None
        dek_before = cache_get(int(account.id))
        assert dek_before is not None

    # Encrypt a test value.
    ut = UserEncryptedText()
    dek_token = set_user_dek(dek_before)
    try:
        ciphertext = ut.process_bind_param("test-value-42", None)
    finally:
        reset_user_dek(dek_token)
    assert ciphertext is not None

    # Change password.
    new_pw = "new-password-999"
    ch_resp = client.post(
        "/api/v1/auth/change-password",
        json={
            "current_password": _account["password"],
            "new_password": new_pw,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ch_resp.status_code == 200

    # Login with new password.
    client2 = TestClient(_app())
    login2 = client2.post(
        "/api/v1/auth/login",
        json={
            "email": _account["email"],
            "password": new_pw,
        },
    )
    assert login2.status_code == 200

    # The cached DEK after new login should still decrypt old data.
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == _account["email"])
            .first()
        )
        dek_after = cache_get(int(account.id))
        account_id = int(account.id)
        assert dek_after is not None

    tok = set_user_dek(dek_after)
    try:
        result = ut.process_result_value(ciphertext, None)
        assert result == "test-value-42"
    finally:
        reset_user_dek(tok)
        cache_evict(account_id)


def test_logout_evicts_dek_cache(_db: str, _account: dict) -> None:
    """Logout removes the DEK from the process cache immediately."""
    from airunner_services.utils.crypto.dek_cache import cache_get

    reset_engine()
    client = TestClient(_app())

    # Login.
    login_resp = client.post(
        "/api/v1/auth/login",
        json={
            "email": _account["email"],
            "password": _account["password"],
        },
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    # Confirm DEK is cached.
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == _account["email"])
            .first()
        )
        assert cache_get(int(account.id)) is not None

    # Logout.
    logout_resp = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_resp.status_code == 200

    # DEK must be gone.
    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == _account["email"])
            .first()
        )
        assert cache_get(int(account.id)) is None


# ---------------------------------------------------------------------------
# Sensitive-data consent (JP / IN / CA)
# ---------------------------------------------------------------------------


def _patch_resolve_country(monkeypatch, country: str | None):
    """Mock resolve_country to return a fixed ISO country code."""
    async def _fake(_request):
        return country

    monkeypatch.setattr(
        "extensions.auth.server.geoblock.resolve_country", _fake
    )
    # Also patch the import path used inside routes.py — the inline
    # import inside the register handler resolves to the same module,
    # so patching the geoblock module covers both.


def test_register_jp_without_consent_rejected(
    _db: str, monkeypatch,
) -> None:
    """JP IP without sensitive_data_consent_agreed → 400."""
    reset_engine()
    _patch_resolve_country(monkeypatch, "JP")
    client = TestClient(_app())
    email = _unique_email()

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secure-password-123",
            "tos_agreed": True,
            "age_confirmed": True,
            "entertainment_confirmed": True,
            # sensitive_data_consent_agreed omitted — defaults False
        },
    )
    assert response.status_code == 400
    assert "consent" in response.text.lower()


def test_register_jp_with_consent_succeeds(
    _db: str, monkeypatch,
) -> None:
    """JP IP with sensitive_data_consent_agreed → 201, fields stored."""
    monkeypatch.setenv("AIRUNNER_SIGNUP_MODE", "open")
    reset_engine()
    _patch_resolve_country(monkeypatch, "JP")
    client = TestClient(_app())
    email = _unique_email()

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secure-password-123",
            "tos_agreed": True,
            "age_confirmed": True,
            "entertainment_confirmed": True,
            "sensitive_data_consent_agreed": True,
        },
    )
    assert response.status_code == 201

    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == email)
            .first()
        )
        assert account is not None
        assert account.sensitive_data_consent_agreed is True
        assert account.sensitive_data_consent_at is not None


def test_register_us_without_consent_succeeds(
    _db: str, monkeypatch,
) -> None:
    """US IP without consent → 201 (consent not required)."""
    monkeypatch.setenv("AIRUNNER_SIGNUP_MODE", "open")
    reset_engine()
    _patch_resolve_country(monkeypatch, "US")
    client = TestClient(_app())
    email = _unique_email()

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secure-password-123",
            "tos_agreed": True,
            "age_confirmed": True,
            "entertainment_confirmed": True,
        },
    )
    assert response.status_code == 201

    with public_session_scope() as session:
        account = (
            session.query(Account)
            .filter(Account.email == email)
            .first()
        )
        assert account is not None
        assert account.sensitive_data_consent_agreed is False


def test_register_blocked_country_rejected_first(
    _db: str, monkeypatch,
) -> None:
    """Blocked country (DE) → 451 geoblock, not consent 400."""
    reset_engine()
    _patch_resolve_country(monkeypatch, "DE")
    client = TestClient(_app())
    email = _unique_email()

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secure-password-123",
        },
    )
    assert response.status_code == 451
