"""Auth extension — REST API routes.

Endpoints:
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- POST /api/v1/auth/refresh
- POST /api/v1/auth/logout
- GET  /api/v1/auth/me
- GET  /api/v1/auth/verify
- POST /api/v1/auth/send-verification
- POST /api/v1/auth/password-reset/request
- POST /api/v1/auth/password-reset/confirm
- GET  /api/v1/auth/oauth/google/login
- GET  /api/v1/auth/oauth/google/callback
- POST /api/v1/auth/oauth/exchange
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import os
import secrets
from urllib.parse import urlencode
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func

from airunner_services.conf import settings
from airunner_services.database.session import (
    public_session_scope,
    session_scope as tenant_session_scope,
)
from airunner_services.data.tenant import tenant_schema_for_key
from airunner_services.utils.crypto.dek_cache import cache_evict, cache_set
from airunner_services.utils.crypto.user_envelope import (
    DEFAULT_KDF_PARAMS,
    EnvelopeError,
    decode_salt,
    derive_kek,
    encode_salt,
    generate_dek,
    generate_kdf_salt,
    unwrap_dek,
    wrap_dek,
)

from extensions.auth.server.limiter import limiter
from extensions.auth.server.jwt import (
    create_access_token,
    create_oauth_handoff_token,
    create_refresh_token,
    create_verification_token,
    decode_token,
)
from extensions.auth.server.models import Account
from extensions.auth.server.password_reset_token import PasswordResetToken
from extensions.auth.server.passwords import (
    dummy_verify,
    hash_password,
    verify_password,
)
from extensions.auth.server.dependencies import (
    require_auth,
    require_superuser,
)
from extensions.auth.server.email import (
    send_password_reset_email,
    send_verification_email,
)
from extensions.auth.server.oauth import (
    consume_state,
    decode_oauth_state,
    exchange_code,
    get_google_auth_url,
)
from extensions.auth.server.twitch_oauth import (
    consume_state as consume_twitch_state,
    exchange_code as exchange_twitch_code,
    get_twitch_auth_url,
)
from airunner_services.contract_enums import ModelService

router = APIRouter()

# Keep references to background email-send tasks so they aren't
# garbage-collected before the event loop runs them.
_background_tasks: set[asyncio.Task] = set()

# Include waitlist router under the auth prefix so its endpoints are
# available at /api/v1/auth/waitlist/...
from extensions.auth.server.waitlist_routes import (
    router as waitlist_router,
)
router.include_router(waitlist_router, prefix="/waitlist")


# ── Invite-code gate ────────────────────────────────────────────────

_INVITE_ENV = "AIRUNNER_INVITE_CODE"
_SIGNUP_MODE_ENV = "AIRUNNER_SIGNUP_MODE"


def _signup_mode() -> str:
    """Return 'waitlist' or 'open' (default waitlist).

    Resolution order:
    1. ``AIRUNNER_SIGNUP_MODE`` env var — deploy-time override.
    2. ``SIGNUP_MODE`` from the settings overlay — a project can
       declare its default (e.g. UwUchat sets ``"open"``).
    3. ``"waitlist"`` — the historical default.
    """
    env_mode = os.environ.get(_SIGNUP_MODE_ENV, "").strip()
    if env_mode:
        return env_mode
    return str(
        settings.get("SIGNUP_MODE", "waitlist") or "waitlist"
    ).strip()


def _check_invite_code(supplied: str) -> None:
    """Raise 403 if invite codes are enabled and the code is wrong."""
    required = os.environ.get(_INVITE_ENV, "").strip()
    if not required:
        return
    if not supplied or supplied.strip() != required:
        raise HTTPException(
            status_code=403,
            detail="Invalid invite code.",
        )


def _check_registration_gate(
    invite_code: str,
    waitlist_token: str,
) -> None:
    """Enforce the combined invite-code + waitlist registration gate.

    Gating order:
    1. Valid AIRUNNER_INVITE_CODE → bypass (unchanged behaviour).
    2. Else, if AIRUNNER_SIGNUP_MODE == "waitlist":
       - Valid unexpired unconsumed waitlist_token → allow.
       - Else → 403 with detail_code "waitlist_token_required".
    3. Else ("open" mode) → existing _check_invite_code only.
    """
    required = os.environ.get(_INVITE_ENV, "").strip()
    if required:
        if invite_code.strip() == required:
            return
        # INVITE_CODE is set and the supplied code is wrong — try
        # waitlist token before rejecting.
        if _signup_mode() == "waitlist":
            if _try_waitlist_token(waitlist_token.strip()):
                return
            raise HTTPException(
                status_code=403,
                detail="Invalid invite code.",
            )
        raise HTTPException(
            status_code=403,
            detail="Invalid invite code.",
        )
    # No INVITE_CODE set.
    if _signup_mode() == "waitlist":
        if _try_waitlist_token(waitlist_token.strip()):
            return
        raise HTTPException(
            status_code=403,
            detail={
                "detail_code": "waitlist_token_required",
                "message": (
                    "Registration requires a waitlist invite token."
                ),
            },
        )
    # Open mode — no gate.


def _try_waitlist_token(raw_token: str) -> bool:
    """Return True if *raw_token* is a valid unexpired waitlist invite."""
    if not raw_token:
        return False
    from extensions.auth.server.waitlist_service import (
        redeem_invite_token,
    )
    entry = redeem_invite_token(raw_token)
    return entry is not None


# nosemgrep: missing-auth-dependency (public invite-required endpoint)
@router.get(
    "/invite-required",
    summary="Return whether an invite code is required for registration",
)
async def invite_required() -> dict:
    """Public endpoint that tells the frontend whether to show the
    invite-code field on the registration form."""
    required = os.environ.get(_INVITE_ENV, "").strip()
    return {
        "required": bool(required),
        "signup_mode": _signup_mode(),
    }


# ── Request / Response schemas ──────────────────────────────────────


# ISO 3166-1 alpha-2 codes for jurisdictions where sensitive-data
# consent is required at registration.  These are consent-based
# privacy regimes (Japan APPI, India DPDP Act, Canada PIPEDA) that
# lack GDPR's default-prohibition posture — served with an explicit
# consent flow rather than a hard block.
_SENSITIVE_CONSENT_COUNTRIES: frozenset[str] = frozenset(
    {"JP", "IN", "CA"}
)


class RegisterRequest(BaseModel):
    email: str
    username: str = ""  # Deprecated — server auto-generates, field kept for
    password: str       # backward compat with clients that still send it.
    tos_agreed: bool = False
    age_confirmed: bool = False
    entertainment_confirmed: bool = False
    sensitive_data_consent_agreed: bool = False
    invite_code: str = ""
    waitlist_token: str = ""


class AgreeTosRequest(BaseModel):
    tos_agreed: bool
    age_confirmed: bool
    entertainment_confirmed: bool
    sensitive_data_consent_agreed: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    tenant_key: str


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: int
    email: str
    username: str
    is_verified: bool
    is_superuser: bool
    is_suspended: bool
    tos_agreed: bool
    sensitive_data_consent_agreed: bool
    created_at: str


class VerifyResponse(BaseModel):
    message: str
    already_verified: bool = False


class SendVerificationResponse(BaseModel):
    message: str
    sent: bool


# ── Registration ────────────────────────────────────────────────────


# nosemgrep: missing-auth-dependency (public register endpoint)
@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    response_model=TokenResponse,
)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest) -> TokenResponse:
    """Register a new user, create their tenant schema, and return
    tokens."""

    # ── Geoblock EU/UK users ────────────────────────────────────────
    from extensions.auth.server.geoblock import (
        check_geoblock,
        resolve_country,
    )

    geoblock_msg = await check_geoblock(request)
    if geoblock_msg:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=geoblock_msg,
        )

    # ── Sensitive-data consent for JP/IN/CA ─────────────────────────
    country = await resolve_country(request)
    if (
        country in _SENSITIVE_CONSENT_COUNTRIES
        and not body.sensitive_data_consent_agreed
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Your region requires additional consent before "
                "registration can proceed. The AI companion remembers "
                "information shared in conversation, including "
                "information that may fall into sensitive categories "
                "(health, religious or philosophical beliefs, "
                "political opinions, sexual orientation, etc.), "
                "for the purpose of your own conversational "
                "experience only. This data is never sold or used "
                "for analytics. Please check the "
                "\"sensitive_data_consent_agreed\" box to confirm "
                "you understand and agree."
            ),
        )

    _check_registration_gate(body.invite_code, body.waitlist_token)

    # Validate inputs
    email = body.email.strip().lower()
    # Username is auto-generated server-side. The field is kept on
    # RegisterRequest for backward compat with old clients that send
    # it; any value they provide is silently ignored.
    username = f"user_{uuid.uuid4().hex[:8]}"
    _validate_password_or_raise(body.password)
    if settings.AUTH_REQUIRE_TOS and not (
        body.tos_agreed
        and body.age_confirmed
        and body.entertainment_confirmed
    ):
        raise HTTPException(
            status_code=422,
            detail="Agreement required",
        )

    with public_session_scope() as session:
        # Check uniqueness — email only (username is always random).
        existing = session.query(Account).filter(
            Account.email == email
        ).first()
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="Email already registered",
            )

        # Create tenant schema name — pure UUID, no username embedded.
        raw_key = uuid.uuid4().hex
        tenant_schema = tenant_schema_for_key(raw_key)

        # Hash password and create account
        pw_hash = hash_password(body.password)
        now = datetime.datetime.now(datetime.timezone.utc)
        client_ip = request.client.host if request.client else None
        tos_at = now if body.tos_agreed else None
        sdc_at = now if body.sensitive_data_consent_agreed else None

        # ── Generate per-user key envelope at registration ──────
        salt = generate_kdf_salt()
        encoded_salt = encode_salt(salt)
        kek = derive_kek(body.password, salt)
        dek = generate_dek()
        wrapped = wrap_dek(dek, kek)

        account = Account(
            email=email,
            username=username,
            password_hash=pw_hash,
            tenant_schema=tenant_schema,
            auth_provider=ModelService.LOCAL.value,
            created_at=now,
            tos_agreed=body.tos_agreed,
            age_confirmed=body.age_confirmed,
            entertainment_confirmed=body.entertainment_confirmed,
            tos_agreed_at=tos_at,
            tos_agreed_ip=client_ip if body.tos_agreed else None,
            sensitive_data_consent_agreed=(
                body.sensitive_data_consent_agreed
            ),
            sensitive_data_consent_at=sdc_at,
            sensitive_data_consent_ip=(
                client_ip
                if body.sensitive_data_consent_agreed
                else None
            ),
            wrapped_dek=wrapped,
            dek_kdf_salt=encoded_salt,
            dek_kdf_params=dict(DEFAULT_KDF_PARAMS),
            dek_version=1,
        )
        session.add(account)
        session.flush()  # Get the account ID

        # Consume waitlist invite token atomically with account creation.
        waitlist_token = body.waitlist_token.strip()
        if waitlist_token:
            from extensions.auth.server.waitlist_service import (
                redeem_invite_token,
            )
            entry = redeem_invite_token(
                waitlist_token, _session=session,
            )
            if entry is not None:
                now = datetime.datetime.now(datetime.timezone.utc)
                entry.converted_account_id = account.id
                entry.converted_at = now
                session.add(entry)

        # Build tokens before session closes
        token_version = account.token_version or 0
        access_token = create_access_token(
            account.id, tenant_schema, token_version
        )
        refresh_token = create_refresh_token(account.id, token_version)
        account_id = account.id

    # Create tenant schema + seed default data outside the public
    # session so the tenant session can use its own connection.
    # Provisioning failure must not prevent registration — the account
    # is already committed.  The tenant will be lazily provisioned on
    # the first authenticated request via ``_ensure_tenant_ready``.
    try:
        _provision_tenant(tenant_schema)

        # Cache the DEK so the new user's first request can encrypt.
        cache_set(account_id, dek)
    except Exception:
        import logging
        _log = logging.getLogger("airunner.auth.register")
        _log.exception(
            "Tenant provisioning failed for %s (account %d). "
            "Will retry on first authenticated request.",
            tenant_schema,
            account_id,
        )

    # Send verification email (offloaded to thread to avoid blocking the
    # event loop — failure must not prevent registration)
    try:
        verif_token = create_verification_token(account_id)
        await asyncio.to_thread(
            send_verification_email, email, username, verif_token
        )
    except Exception:
        pass  # Email failure should not prevent account creation

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        tenant_key=tenant_schema,
    )


def _provision_tenant(tenant_schema: str) -> None:
    """Create database schema for a new tenant and seed default rows."""
    from airunner_services.database.setup_database import (
        setup_database,
    )
    from airunner_services.database.db.engine import (
        create_configured_engine,
    )
    from sqlalchemy import text

    db_url = settings.DATABASE_URL
    if db_url.lower().startswith("postgresql"):
        # Create schema and run migrations
        base_engine = create_configured_engine(db_url)
        with base_engine.begin() as connection:
            connection.execute(
                text(f"CREATE SCHEMA IF NOT EXISTS {tenant_schema}")
            )
        base_engine.dispose()

        tenant_url = _tenant_db_url(db_url, tenant_schema)
        setup_database(db_url=tenant_url)
        _seed_tenant_defaults(tenant_url)
    else:
        # SQLite single-user: no per-user isolation needed
        setup_database(db_url=db_url)


def _seed_tenant_defaults(tenant_url: str) -> None:
    """Seed default rows into a freshly provisioned tenant schema."""
    from extensions.auth.server.seed import (
        seed_default_chatbot,
    )

    seed_default_chatbot(tenant_url)


def _tenant_db_url(base_url: str, tenant_schema: str) -> str:
    """Build a database URL with a search_path for the given schema."""
    from sqlalchemy.engine import make_url
    from sqlalchemy.engine.url import URL

    url = make_url(base_url)
    query = dict(url.query or {})
    query["options"] = f"-csearch_path={tenant_schema},public"
    new_url = URL.create(
        drivername=url.drivername,
        username=url.username,
        password=url.password,
        host=url.host,
        port=url.port,
        database=url.database,
        query=query,
    )
    return new_url.render_as_string(hide_password=False)


# ── Shared account creation ─────────────────────────────────────────


def _validate_password_or_raise(password: str) -> None:
    """Validate *password* strength and raise if it fails policy.

    Uses the shared ``password_policy`` module (zxcvbn-based) so all
    four call sites stay in sync.  Raises :class:`HTTPException` (400)
    with a user-facing reason for handler callers, or
    :class:`AccountValidationError` for the CLI helper.
    """
    from extensions.auth.server.password_policy import (
        validate_password_strength,
    )

    result = validate_password_strength(password)
    if result.is_valid:
        return
    # The caller context determines which exception type to raise.
    # Handlers catch this and map to HTTPException; the CLI helper
    # maps AccountValidationError to a CLI-friendly error.
    raise AccountValidationError(result.reason)


class AccountValidationError(ValueError):
    """Raised when account inputs fail validation (maps to HTTP 400)."""


class AccountConflictError(ValueError):
    """Raised when email/username already exists (maps to HTTP 409)."""


def create_account(
    email: str,
    password: str,
    username: str | None = None,
    *,
    is_superuser: bool = False,
    is_verified: bool = True,
    provision_tenant: bool = True,
) -> tuple[int, str]:
    """Create a local account row and (optionally) provision its tenant.

    Shared by the account-management CLI
    (:func:`extensions.auth.server.manage.cmd_create_user`) and the admin
    ``POST /admin/accounts`` route so the two can't drift.

    If *username* is ``None`` or empty, one is auto-generated as
    ``user_XXXXXXXX`` (random hex).

    Returns ``(account_id, tenant_schema)``. Raises
    :class:`AccountValidationError` for bad inputs and
    :class:`AccountConflictError` when the email is already registered.
    """
    email = email.strip().lower()
    username = (
        username.strip()
        if username and username.strip()
        else f"user_{uuid.uuid4().hex[:8]}"
    )
    _validate_password_or_raise(password)

    # Tenant schema key is a pure UUID — no username embedded.
    raw_key = uuid.uuid4().hex
    tenant_schema = tenant_schema_for_key(raw_key)

    with public_session_scope() as session:
        clash = (
            session.query(Account)
            .filter(Account.email == email)
            .first()
        )
        if clash is not None:
            raise AccountConflictError(
                "Email already registered"
            )

        # ── Generate per-user key envelope ──────────────────────
        salt = generate_kdf_salt()
        encoded_salt = encode_salt(salt)
        kek = derive_kek(password, salt)
        dek = generate_dek()
        wrapped = wrap_dek(dek, kek)

        account = Account(
            email=email,
            username=username,
            password_hash=hash_password(password),
            tenant_schema=tenant_schema,
            auth_provider=ModelService.LOCAL.value,
            is_superuser=is_superuser,
            is_verified=is_verified,
            created_at=datetime.datetime.now(datetime.timezone.utc),
            wrapped_dek=wrapped,
            dek_kdf_salt=encoded_salt,
            dek_kdf_params=dict(DEFAULT_KDF_PARAMS),
            dek_version=1,
        )
        session.add(account)
        session.flush()  # Get the account ID
        account_id = account.id

    # Provision the tenant schema outside the public session so the tenant
    # session can use its own connection.
    if provision_tenant:
        _provision_tenant(tenant_schema)

    return account_id, tenant_schema


# ── Login ───────────────────────────────────────────────────────────


# nosemgrep: missing-auth-dependency (public login endpoint)
@router.post(
    "/login",
    summary="Authenticate and receive JWT tokens",
)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest) -> TokenResponse:
    """Authenticate with email + password and receive JWT tokens."""

    # ── Geoblock EU/UK users ────────────────────────────────────────
    from extensions.auth.server.geoblock import check_geoblock

    geoblock_msg = await check_geoblock(request)
    if geoblock_msg:
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=geoblock_msg,
        )

    email = body.email.strip().lower()

    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.email == email
        ).first()

        if account is None or account.password_hash is None:
            # Spend comparable CPU so timing doesn't reveal whether the
            # email exists (or is an OAuth-only account with no password).
            dummy_verify()
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password",
            )

        if not verify_password(body.password, account.password_hash):
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password",
            )

        if account.deleted:
            raise HTTPException(
                status_code=403,
                detail="This account has been deleted",
            )

        if not account.is_active:
            raise HTTPException(
                status_code=403,
                detail="Account is disabled",
            )

        # ── User-controlled key envelope ──────────────────────────
        # Derive the KEK from the plaintext password (held only for
        # the duration of this request) and cache the unwrapped DEK.
        password = body.password
        _envelope_login_setup(session, account, password)

        # Update last login
        account.last_login = datetime.datetime.now(datetime.timezone.utc)
        session.add(account)
        session.flush()  # Persist the change without closing session

        token_version = account.token_version or 0
        access_token = create_access_token(
            account.id, account.tenant_schema, token_version
        )
        refresh_token = create_refresh_token(account.id, token_version)
        tenant_schema = account.tenant_schema
        account_id = account.id

    # Schedule lazy re-encryption of legacy rows as a background task
    # so login stays fast.  This is fire-and-forget — failures are
    # logged but must not prevent login.
    _ = asyncio.ensure_future(
        asyncio.to_thread(
            _backfill_user_encryption, account_id, password
        )
    )

    # Notify project-specific handlers (e.g. email indexing recovery)
    # that login completed.  SignalMediator dispatch is synchronous and
    # local (in-process, no serialization), so passing the plaintext
    # password is safe — same trust boundary as the function-call it
    # replaces.  A handler that needs to do slow work must dispatch
    # to its own background thread.  Wrap in try/except so a broken
    # signal handler cannot affect login.
    from airunner_services.contract_enums import SignalCode
    from airunner_services.utils.application.signal_mediator import (
        SignalMediator,
    )

    try:
        from airunner_services.data.tenant import tenant_key_from_schema

        SignalMediator().emit_signal(
            SignalCode.USER_LOGIN_COMPLETE,
            {
                "account_id": account_id,
                "password": password,
                "tenant_key": tenant_key_from_schema(tenant_schema),
            },
        )
    except Exception:
        logging.getLogger(__name__).warning(
            "USER_LOGIN_COMPLETE signal handler failed",
            exc_info=True,
        )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        tenant_key=tenant_schema,
    )


# ── Key-envelope helpers ─────────────────────────────────────────────


def _envelope_login_setup(session, account, password: str) -> None:
    """Derive KEK from password, unwrap (or backfill) the DEK, cache it.

    Called inside the public-schema session during login, after password
    verification succeeds but before tokens are issued.  The plaintext
    *password* is never persisted and never leaves this function's scope
    beyond the KEK derivation.
    """
    from airunner_services.utils.crypto.dek_cache import cache_set
    from airunner_services.utils.crypto.user_envelope import (
        DEFAULT_KDF_PARAMS,
        decode_salt,
        derive_kek,
        encode_salt,
        generate_dek,
        generate_kdf_salt,
        unwrap_dek,
        wrap_dek,
    )

    import logging as _logging
    _log = _logging.getLogger("airunner.auth.envelope")

    if account.wrapped_dek is None:
        # ── Lazy backfill: first login after migration ───────────
        salt = generate_kdf_salt()
        encoded_salt = encode_salt(salt)
        kek = derive_kek(password, salt)
        dek = generate_dek()
        wrapped = wrap_dek(dek, kek)

        account.wrapped_dek = wrapped
        account.dek_kdf_salt = encoded_salt
        account.dek_kdf_params = dict(DEFAULT_KDF_PARAMS)
        account.dek_version = 1
        session.add(account)
        session.flush()

        cache_set(int(account.id), dek)
        _log.info(
            "DEK backfilled for account %d (first envelope login)",
            account.id,
        )
    else:
        # ── Normal unwrap ────────────────────────────────────────
        try:
            salt = decode_salt(account.dek_kdf_salt)
            params = account.dek_kdf_params or dict(DEFAULT_KDF_PARAMS)
            kek = derive_kek(password, salt, params=params)
            dek = unwrap_dek(account.wrapped_dek, kek)
            cache_set(int(account.id), dek)
        except Exception:
            _log.exception(
                "DEK unwrap failed for account %d — wrong password or "
                "corrupted wrapped key",
                account.id,
            )
            # Don't block login — the user's session still works, but
            # encryption/decryption of per-user columns will fail.
            pass


def _backfill_user_encryption(account_id: int, password: str) -> None:
    """Re-encrypt legacy rows from global key → user's DEK.

    Runs as a background task after login (fire-and-forget).  Walks the
    user's tenant schema and re-encrypts any rows in
    ``agent_memories``, ``conversation_turns``, ``knowledge_facts``,
    ``conversations``, and ``summaries`` that are still encrypted with
    the global key.

    This is a best-effort operation — failures are logged and retried
    on the next login.
    """
    import logging as _logging

    _log = _logging.getLogger("airunner.auth.backfill")

    try:
        from airunner_services.database.session import (
            public_session_scope,
        )
        from extensions.auth.server.models import Account

        # Look up the tenant schema for this account and capture
        # envelope fields before the session closes (DetachedInstanceError).
        with public_session_scope() as pub_session:
            account = (
                pub_session.query(Account)
                .filter(Account.id == account_id)
                .first()
            )
            if account is None or account.wrapped_dek is None:
                _log.warning(
                    "Backfill skipped for account %d: no envelope",
                    account_id,
                )
                return
            tenant_schema = account.tenant_schema
            dek_kdf_salt = account.dek_kdf_salt
            dek_kdf_params = account.dek_kdf_params
            wrapped_dek = account.wrapped_dek

        from airunner_services.utils.crypto.dek_cache import cache_set
        from airunner_services.utils.crypto.user_envelope import (
            decode_salt,
            derive_kek,
            unwrap_dek,
        )

        # Derive the DEK for re-encryption.
        salt = decode_salt(dek_kdf_salt)
        kek = derive_kek(password, salt, params=dek_kdf_params)
        dek = unwrap_dek(wrapped_dek, kek)
        cache_set(account_id, dek)

        from airunner_services.utils.crypto.data_encryption import (
            decrypt_bytes,
            get_keyring,
        )

        keyring = get_keyring(required=False)
        if keyring is None:
            _log.info("No global keyring — backfill not needed")
            return

        from airunner_services.data.tenant import (
            set_tenant_key,
            reset_tenant_key,
            tenant_key_from_schema,
        )

        tenant_key = tenant_key_from_schema(tenant_schema)
        tenant_token = set_tenant_key(tenant_key)

        try:
            from airunner_services.database.session import (
                session_scope as tenant_session_scope,
            )

            with tenant_session_scope() as ts:
                _backfill_table(
                    ts,
                    _log,
                    account_id,
                    "agent_memories",
                    "summary",
                    keyring,
                    dek,
                )
                _backfill_table(
                    ts,
                    _log,
                    account_id,
                    "conversation_turns",
                    "content",
                    keyring,
                    dek,
                )
                _backfill_table(
                    ts,
                    _log,
                    account_id,
                    "knowledge_facts",
                    "fact_text",
                    keyring,
                    dek,
                )
                _backfill_table(
                    ts,
                    _log,
                    account_id,
                    "conversations",
                    "summary",
                    keyring,
                    dek,
                )
                _backfill_table(
                    ts,
                    _log,
                    account_id,
                    "conversations",
                    "value",
                    keyring,
                    dek,
                )
                _backfill_table(
                    ts,
                    _log,
                    account_id,
                    "summaries",
                    "content",
                    keyring,
                    dek,
                )
        finally:
            reset_tenant_key(tenant_token)

        _log.info(
            "Backfill complete for account %d",
            account_id,
        )
    except Exception:
        _log.exception(
            "Backfill failed for account %d",
            account_id,
        )


def _backfill_table(
    ts,
    log,
    account_id: int,
    table_name: str,
    column_name: str,
    keyring,
    dek: bytes,
) -> None:
    """Re-encrypt *column_name* in *table_name* with the user's DEK."""
    from sqlalchemy import text
    from cryptography.fernet import Fernet

    # dek is already a base64-urlsafe-encoded Fernet key (it comes
    # straight from Fernet.generate_key() — see generate_dek()), so it
    # must be passed to Fernet() directly. Re-encoding it here produced
    # a 44-byte "key" instead of the required 32, which is why this
    # backfill was silently failing for every account.
    user_fernet = Fernet(dek)
    global_fernets = [Fernet(k) for k in keyring.decrypt_keys]

    # Fetch rows that still look encrypted (Fernet prefix).
    # table_name/column_name are hardcoded literals from the 6 call
    # sites above -- never request-derived -- so this identifier
    # interpolation is safe (identifiers can't be bind params).
    rows = ts.execute(
        text(
            f"SELECT id, {column_name} FROM {table_name} "  # nosec B608
            f"WHERE {column_name} LIKE 'gAAAAA%'"
        )
    ).fetchall()

    if not rows:
        return

    re_encrypted = 0
    for row_id, ciphertext in rows:
        if ciphertext is None:
            continue
        raw = ciphertext.encode("utf-8")
        # Try global keys
        plaintext = None
        for f in global_fernets:
            try:
                plaintext = f.decrypt(raw)
                break
            except Exception:
                continue
        if plaintext is None:
            continue
        # Re-encrypt with user's DEK
        new_ciphertext = user_fernet.encrypt(plaintext).decode("utf-8")
        # table_name/column_name are hardcoded literals (see above).
        ts.execute(
            text(
                f"UPDATE {table_name} SET {column_name} = :val "  # nosec B608
                f"WHERE id = :rid"
            ),
            {"val": new_ciphertext, "rid": row_id},
        )
        re_encrypted += 1
        if re_encrypted % 100 == 0:
            ts.flush()

    ts.flush()
    log.info(
        "Backfill %s.%s: %d rows re-encrypted for account %d",
        table_name,
        column_name,
        re_encrypted,
        account_id,
    )


# ── Token refresh ───────────────────────────────────────────────────


# nosemgrep: missing-auth-dependency (public token refresh endpoint)
@router.post(
    "/refresh",
    summary="Obtain a new access token using a refresh token",
)
async def refresh(body: RefreshRequest) -> dict:
    """Exchange a refresh token for a new access token."""
    payload = decode_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    account_id = int(payload["sub"])
    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.id == account_id
        ).first()
        if account is None or not account.is_active:
            raise HTTPException(
                status_code=401,
                detail="Account not found or disabled",
            )
        if account.is_banned:
            raise HTTPException(
                status_code=403,
                detail="Account is banned",
            )
        if account.is_suspended:
            raise HTTPException(
                status_code=403,
                detail="Account is suspended",
            )

        # Reject tokens that predate a logout / "sign out everywhere".
        if int(payload.get("ver", 0)) != int(account.token_version or 0):
            raise HTTPException(
                status_code=401,
                detail="Refresh token has been revoked",
            )

        token_version = account.token_version or 0
        new_access = create_access_token(
            account.id, account.tenant_schema, token_version
        )

    return {
        "access_token": new_access,
        "token_type": "bearer",
    }


# ── Current user ────────────────────────────────────────────────────


@router.get(
    "/me",
    summary="Return the currently authenticated user's profile",
)
async def me(account_id: int = Depends(require_auth)) -> MeResponse:
    """Return profile data for the authenticated user."""
    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.id == account_id
        ).first()
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

        return MeResponse(
            id=account.id,
            email=account.email,
            username=account.username,
            is_verified=account.is_verified,
            is_superuser=account.is_superuser,
            is_suspended=bool(account.is_suspended),
            tos_agreed=bool(account.tos_agreed),
            sensitive_data_consent_agreed=bool(
                account.sensitive_data_consent_agreed
            ),
            created_at=(
                account.created_at.isoformat()
                if account.created_at
                else ""
            ),
        )


# ── Logout (revoke refresh tokens) ──────────────────────────────────


@router.post(
    "/logout",
    summary="Revoke all outstanding refresh tokens for the current user",
)
async def logout(account_id: int = Depends(require_auth)) -> dict:
    """Invalidate every refresh token issued to the user.

    Bumps the account's ``token_version`` so existing refresh tokens stop
    working ("sign out everywhere").  Already-issued access tokens remain
    valid until they expire (default 15 min); keep the access TTL short.
    """
    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.id == account_id
        ).first()
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        account.token_version = (account.token_version or 0) + 1
        session.add(account)

    # Evict the DEK from the process-local cache immediately so a
    # stolen access token can't decrypt user data indefinitely.
    cache_evict(account_id)

    return {"message": "Logged out"}


# ── Change password (authenticated, no data loss) ────────────────────


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post(
    "/change-password",
    summary="Change password without losing encrypted history",
)
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    account_id: int = Depends(require_auth),
) -> dict:
    """Change the account password while preserving the DEK.

    Because the user provides their current password, the existing DEK
    can be unwrapped with the old KEK and re-wrapped under a new KEK
    derived from the new password — zero data loss.

    This is the safe, authenticated password-change path.  The
    token-based forgot-password flow (``/password-reset/confirm``)
    cannot recover the DEK (no old password available) and must
    generate a fresh one, losing encrypted history.
    """
    _validate_password_or_raise(body.new_password)

    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.id == account_id,
        ).first()

        if account is None or account.password_hash is None:
            raise HTTPException(
                status_code=400,
                detail="Account not found or has no password",
            )

        if not verify_password(
            body.current_password, account.password_hash
        ):
            raise HTTPException(
                status_code=400,
                detail="Current password is incorrect",
            )

        # ── Re-wrap the DEK under the new password ──────────────
        if account.wrapped_dek is not None:
            # Unwrap with old KEK
            try:
                salt = decode_salt(account.dek_kdf_salt)
                params = (
                    account.dek_kdf_params
                    or dict(DEFAULT_KDF_PARAMS)
                )
                old_kek = derive_kek(
                    body.current_password, salt, params=params
                )
                dek = unwrap_dek(account.wrapped_dek, old_kek)
            except EnvelopeError:
                raise HTTPException(
                    status_code=400,
                    detail="Current password is incorrect",
                ) from None

            # Re-wrap with new KEK
            new_salt = generate_kdf_salt()
            new_kek = derive_kek(body.new_password, new_salt)
            account.wrapped_dek = wrap_dek(dek, new_kek)
            account.dek_kdf_salt = encode_salt(new_salt)
            account.dek_kdf_params = dict(DEFAULT_KDF_PARAMS)
            account.dek_version = (account.dek_version or 1) + 1

            # Refresh the cache with the (unchanged) DEK
            cache_set(account_id, dek)

        # Update password hash and bump token version
        account.password_hash = hash_password(body.new_password)
        account.token_version = (account.token_version or 0) + 1
        session.add(account)

    return {"message": "Password changed successfully."}


# ── Email verification ──────────────────────────────────────────────


# nosemgrep: missing-auth-dependency (public email verify endpoint)
@router.get(
    "/verify",
    summary="Verify an email address using a verification token",
    response_model=VerifyResponse,
)
async def verify(token: str) -> VerifyResponse:
    """Verify a user's email address using a JWT verification token."""
    payload = decode_token(token, expected_type="verify")
    if payload is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired verification token",
        )

    account_id = int(payload["sub"])
    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.id == account_id
        ).first()
        if account is None:
            raise HTTPException(
                status_code=404,
                detail="Account not found",
            )

        if account.is_verified:
            return VerifyResponse(
                message="Email already verified",
                already_verified=True,
            )

        account.is_verified = True
        session.add(account)

    return VerifyResponse(message="Email verified successfully")


@router.post(
    "/send-verification",
    summary="Send a verification email to the currently authenticated user",
    response_model=SendVerificationResponse,
)
@limiter.limit("3/minute")
async def send_verification(
    request: Request,
    account_id: int = Depends(require_auth),
) -> SendVerificationResponse:
    """Send a verification email to the currently authenticated user."""
    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.id == account_id
        ).first()
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

        if account.is_verified:
            raise HTTPException(
                status_code=400,
                detail="Email already verified",
            )

        email = account.email
        username = account.username
        account_id = account.id
        token = create_verification_token(account_id)

    sent = await asyncio.to_thread(
        send_verification_email, email, username, token
    )

    return SendVerificationResponse(
        message=(
            "Verification email sent"
            if sent
            else "Failed to send verification email. SMTP may not be configured."
        ),
        sent=sent,
    )




# ── Password reset ──────────────────────────────────────────────────


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str


class PasswordResetResponse(BaseModel):
    message: str


# Token expiry: 1 hour.
_RESET_TOKEN_TTL_SECONDS = 3600


def _make_reset_token() -> tuple[str, str]:
    """Return (raw_token, token_hash)."""
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


# nosemgrep: missing-auth-dependency (public password-reset request endpoint)
@router.post(
    "/password-reset/request",
    summary="Request a password-reset email",
    response_model=PasswordResetResponse,
)
@limiter.limit("5/hour")
async def password_reset_request(
    request: Request,
    body: PasswordResetRequest,
) -> PasswordResetResponse:
    """Send a password-reset email if the account exists.

    Returns the same 200 response regardless of whether the email is
    registered — this prevents user enumeration.  The email send is
    fired in the background so both paths return in roughly the same
    time, closing a timing side-channel.
    """
    email = body.email.strip().lower()

    should_send = False
    username = ""
    raw_token = ""

    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.email == email,
        ).first()

        if (
            account is not None
            and not account.deleted
            and account.is_active
            and account.password_hash is not None
        ):
            raw_token, token_hash = _make_reset_token()
            now = datetime.datetime.now(datetime.timezone.utc)
            expires_at = now + datetime.timedelta(
                seconds=_RESET_TOKEN_TTL_SECONDS,
            )
            session.add(PasswordResetToken(
                account_id=account.id,
                token_hash=token_hash,
                expires_at=expires_at,
                created_at=now,
            ))
            session.flush()
            username = account.username
            should_send = True

    if should_send:
        task = asyncio.ensure_future(
            asyncio.to_thread(
                send_password_reset_email, email, username, raw_token,
            ),
        )
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return PasswordResetResponse(
        message="If that email exists, a reset link has been sent.",
    )


# nosemgrep: missing-auth-dependency (public password-reset confirm endpoint)
@router.post(
    "/password-reset/confirm",
    summary="Confirm a password reset with a valid token",
    response_model=PasswordResetResponse,
)
@limiter.limit("10/hour")
async def password_reset_confirm(
    request: Request,
    body: PasswordResetConfirmRequest,
) -> PasswordResetResponse:
    """Validate the reset token and change the account password.

    On success, bumps ``token_version`` to invalidate all existing
    sessions/refresh tokens for the account.
    """
    _validate_password_or_raise(body.new_password)

    token_hash = hashlib.sha256(
        body.token.encode(),
    ).hexdigest()
    now = datetime.datetime.now(datetime.timezone.utc)

    with public_session_scope() as session:
        token_row = (
            session.query(PasswordResetToken)
            .filter(
                PasswordResetToken.token_hash == token_hash,
            )
            .first()
        )

        if token_row is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired reset token",
            )

        if token_row.used:
            raise HTTPException(
                status_code=400,
                detail="This reset link has already been used",
            )

        if token_row.expires_at < now:
            raise HTTPException(
                status_code=400,
                detail="This reset link has expired",
            )

        account = session.query(Account).filter(
            Account.id == token_row.account_id,
        ).first()

        if account is None or not account.is_active or account.deleted:
            raise HTTPException(
                status_code=400,
                detail="Invalid or expired reset token",
            )

        # ── Key-envelope: password reset invalidates the old KEK ──
        # Without the old password, the DEK cannot be unwrapped.
        # This is intentional — a true user-controlled key means
        # the server cannot recover encrypted history without the
        # password.  The user is warned; encrypted content becomes
        # permanently unreadable.
        had_envelope = account.wrapped_dek is not None
        if had_envelope:
            # Generate a fresh DEK + salt for the new password.
            # Old ciphertext will be unreadable — this is surfaced
            # to the caller in the response.
            salt = generate_kdf_salt()
            encoded_salt = encode_salt(salt)
            kek = derive_kek(body.new_password, salt)
            dek = generate_dek()
            wrapped = wrap_dek(dek, kek)
            account.wrapped_dek = wrapped
            account.dek_kdf_salt = encoded_salt
            account.dek_kdf_params = dict(DEFAULT_KDF_PARAMS)
            account.dek_version = (account.dek_version or 1) + 1
            cache_evict(int(token_row.account_id))

        # Hash new password and update account.
        account.password_hash = hash_password(body.new_password)
        account.token_version = (account.token_version or 0) + 1
        session.add(account)

        # Mark token as used.
        token_row.used = True
        session.add(token_row)

    msg = "Password has been reset successfully."
    if had_envelope:
        msg += (
            " Your previously encrypted conversation history is no "
            "longer readable — the encryption key was tied to your "
            "old password."
        )

    return PasswordResetResponse(message=msg)


# ── ToS post-agreement (OAuth new users) ────────────────────────────


@router.post(
    "/agree-tos",
    summary="Record ToS agreement for an authenticated user",
)
@limiter.limit("10/minute")
async def agree_tos(
    request: Request,
    body: AgreeTosRequest,
    account_id: int = Depends(require_auth),
) -> dict:
    """Record explicit ToS agreement after OAuth sign-up.

    Called by the frontend ToS interstitial for new Google OAuth users
    who bypass the registration form.
    """
    if not (
        body.tos_agreed
        and body.age_confirmed
        and body.entertainment_confirmed
    ):
        raise HTTPException(
            status_code=422,
            detail="All agreement fields must be true",
        )

    # ── Sensitive-data consent for JP/IN/CA ─────────────────────────
    from extensions.auth.server.geoblock import (
        resolve_country,
    )

    country = await resolve_country(request)
    if (
        country in _SENSITIVE_CONSENT_COUNTRIES
        and not body.sensitive_data_consent_agreed
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Your region requires additional consent before "
                "proceeding. The AI companion remembers information "
                "shared in conversation, including information that "
                "may fall into sensitive categories (health, "
                "religious or philosophical beliefs, political "
                "opinions, sexual orientation, etc.), for the "
                "purpose of your own conversational experience "
                "only. This data is never sold or used for "
                "analytics. Please confirm the "
                "\"sensitive_data_consent_agreed\" checkbox."
            ),
        )

    now = datetime.datetime.now(datetime.timezone.utc)
    client_ip = request.client.host if request.client else None
    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.id == account_id
        ).first()
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        account.tos_agreed = True
        account.age_confirmed = True
        account.entertainment_confirmed = True
        account.tos_agreed_at = now
        account.tos_agreed_ip = client_ip
        if body.sensitive_data_consent_agreed:
            account.sensitive_data_consent_agreed = True
            account.sensitive_data_consent_at = now
            account.sensitive_data_consent_ip = client_ip
        session.add(account)
    return {"message": "Agreement recorded"}


# ── Self-service account deletion (GDPR right to erasure) ───────────


class DeleteMeRequest(BaseModel):
    """Confirmation body for self-service account deletion.

    For local (password-based) accounts, the current password is required
    as re-authentication before the irreversible delete proceeds.
    OAuth-only accounts (no password_hash) skip the password check.
    """
    password: str = ""


@router.post(
    "/me/delete",
    summary="Delete the authenticated user's own account (GDPR right to erasure)",
)
@limiter.limit("1/hour")
async def delete_me(
    request: Request,
    body: DeleteMeRequest,
    account_id: int = Depends(require_auth),
) -> dict:
    """Permanently delete the authenticated user's account.

    Requires password re-authentication (similar to the change-password
    flow).  All associated data is destroyed:

    - The account row is deleted.
    - The tenant schema is dropped (``CASCADE`` removes all tables).
    - ``PipelineTokenUsage`` rows are deleted (pure usage tracking).
    - ``WaitlistEntry`` is anonymised (``converted_account_id`` set to
      null — the entry itself has no PII beyond the email, which is
      already stored independently).
    - ``UserPromotion`` rows are deleted.
    - ``PromotionCode`` rows are anonymised (``created_by_account_id``
      set to null).
    - ``PasswordResetToken`` rows are deleted.

    This is permanent and irreversible.
    """
    from airunner_services.database.models.pipeline_token_usage import (
        PipelineTokenUsage,
    )
    from extensions.auth.server.waitlist_entry import WaitlistEntry

    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.id == account_id
        ).first()
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

        # ── Re-authentication ────────────────────────────────────
        if account.password_hash is not None:
            if not body.password:
                raise HTTPException(
                    status_code=400,
                    detail="Password is required to delete your account",
                )
            from extensions.auth.server.passwords import (
                verify_password,
            )
            if not verify_password(
                body.password, account.password_hash
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Password is incorrect",
                )

        tenant_schema = account.tenant_schema

        # ── Purge object-storage files for this tenant ────────
        _purge_log = logging.getLogger(__name__)
        try:
            from airunner_services.storage.backends import (
                get_storage_backend,
            )
            backend = get_storage_backend()
            prefix = f"tenants/{tenant_schema}"
            deleted_count = backend.delete_prefix(prefix)
            _purge_log.info(
                "Object-storage purge for account %d: %d objects deleted",
                account_id,
                deleted_count,
            )
        except Exception:
            _purge_log.warning(
                "Object-storage purge failed for account %d "
                "(files may remain in the bucket)",
                account_id,
                exc_info=True,
            )

        # ── 1. Delete PipelineTokenUsage (pure usage tracking) ──
        session.query(PipelineTokenUsage).filter(
            PipelineTokenUsage.account_id == account_id,
        ).delete(synchronize_session=False)

        # ── 2. Anonymise WaitlistEntry (keep row, drop linkage) ──
        session.query(WaitlistEntry).filter(
            WaitlistEntry.converted_account_id == account_id,
        ).update(
            {"converted_account_id": None},
            synchronize_session=False,
        )

        # ── 3. Delete UserPromotion ──────────────────────────────
        session.query(UserPromotion).filter(
            UserPromotion.account_id == account_id,
        ).delete(synchronize_session=False)

        # ── 4. Anonymise PromotionCode (keep row, drop linkage) ──
        session.query(PromotionCode).filter(
            PromotionCode.created_by_account_id == account_id,
        ).update(
            {"created_by_account_id": None},
            synchronize_session=False,
        )

        # ── 5. Delete PasswordResetToken ─────────────────────────
        session.query(PasswordResetToken).filter(
            PasswordResetToken.account_id == account_id,
        ).delete(synchronize_session=False)

        # ── 6. Delete the account row ────────────────────────────
        session.delete(account)

    # Drop the tenant schema outside the public session so the
    # tenant session can use its own connection.
    _drop_tenant_schema(tenant_schema)

    # Evict DEK from cache
    try:
        from airunner_services.utils.crypto.dek_cache import (
            cache_evict,
        )
        cache_evict(account_id)
    except Exception:
        pass

    return {
        "message": (
            "Account permanently deleted. "
            f"Tenant schema '{tenant_schema}' has been dropped."
        )
    }


# ── Google OAuth ────────────────────────────────────────────────────


# nosemgrep: missing-auth-dependency (public Google OAuth login endpoint)
@router.get(
    "/oauth/google/login",
    summary="Initiate Google OAuth login",
)
async def google_oauth_login() -> RedirectResponse:
    """Redirect the user to the Google OAuth consent screen.

    If Google OAuth is not configured, redirects back to /login with
    an error message.
    """
    site_url = os.environ.get(
        "AIRUNNER_SITE_URL",
        "http://localhost:5173",
    ).strip().rstrip("/")

    auth_url = get_google_auth_url()
    if auth_url is None:
        return RedirectResponse(
            url=f"{site_url}/login?error=google_oauth_not_configured",
            status_code=302,
        )
    return RedirectResponse(url=auth_url, status_code=302)


# nosemgrep: missing-auth-dependency (public Google OAuth callback endpoint)
@router.get(
    "/oauth/google/callback",
    summary="Handle Google OAuth callback",
)
async def google_oauth_callback(
    request: Request,
    code: str,
    state: str,
) -> RedirectResponse:
    """Handle the OAuth callback from Google.

    On success, redirects to ``{SITE_URL}/oauth/callback`` with
    access/refresh tokens as query parameters.  On failure, redirects
    to ``{SITE_URL}/login?error=...``.
    """
    from airunner_services.data.tenant import tenant_schema_for_key

    site_url = os.environ.get(
        "AIRUNNER_SITE_URL",
        "http://localhost:5173",
    ).strip().rstrip("/")

    # Validate CSRF state
    state_payload = decode_oauth_state(state)
    if state_payload is None:
        return RedirectResponse(
            url=f"{site_url}/login?error=invalid_oauth_state",
            status_code=302,
        )
    # Exchange code for user info
    user_info = await exchange_code(code)
    if user_info is None:
        return RedirectResponse(
            url=f"{site_url}/login?error=oauth_failed",
            status_code=302,
        )

    was_new_account = False

    with public_session_scope() as session:
        # Look up by google_id first
        account = session.query(Account).filter(
            Account.google_id == user_info.google_id
        ).first()

        if account is None:
            # Look up by email
            account = session.query(Account).filter(
                Account.email == user_info.email
            ).first()

            if account is not None:
                # Existing account with this email but different provider
                if (
                    account.auth_provider == ModelService.LOCAL.value
                    and account.password_hash is not None
                ):
                    return RedirectResponse(
                        url=(
                            f"{site_url}/login?"
                            f"{urlencode({
                                'error': 'email_exists',
                                'detail': (
                                    'An account with this email already exists. '
                                    'Sign in with your password instead, then '
                                    'link Google in settings.'
                                ),
                            })}"
                        ),
                        status_code=302,
                    )

                # Account exists with same email from Google (edge case)
                # — link the google_id
                account.google_id = user_info.google_id
                account.auth_provider = ModelService.GOOGLE.value
                if user_info.verified_email and not account.is_verified:
                    account.is_verified = True
                session.add(account)
                session.flush()
            else:
                # Block new Google OAuth accounts when invite codes are active.
                _required_code = os.environ.get(_INVITE_ENV, "").strip()
                if _required_code:
                    return RedirectResponse(
                        url=(
                            f"{site_url}/login?"
                            f"{urlencode({'error': 'invite_required'})}"
                        ),
                        status_code=302,
                    )
                # Create new account via Google OAuth
                was_new_account = True

                # Auto-generate random username (internal only).
                username = f"user_{uuid.uuid4().hex[:8]}"

                # Pure UUID tenant key — no username embedded.
                raw_key = uuid.uuid4().hex
                tenant_schema = tenant_schema_for_key(raw_key)

                now = datetime.datetime.now(datetime.timezone.utc)
                account = Account(
                    email=user_info.email,
                    username=username,
                    password_hash=None,   # OAuth-only — no password
                    is_verified=user_info.verified_email,
                    google_id=user_info.google_id,
                    auth_provider="google",
                    tenant_schema=tenant_schema,
                    created_at=now,
                )
                session.add(account)
                session.flush()

        # Update last login
        account.last_login = datetime.datetime.now(datetime.timezone.utc)
        session.add(account)
        session.flush()

        final_account_id = account.id
        final_tenant_schema = account.tenant_schema

    # Provision tenant for newly created accounts
    if was_new_account:
        _provision_tenant(final_tenant_schema)

        # Pre-fill display_name from Google profile so the onboarding
        # NameStep is skippable (matching Steam/Bluesky behaviour).
        from airunner_services.database.models.user import (
            User,
        )
        from airunner_services.database.session import (
            session_scope as _t_session,
        )
        from airunner_services.data.tenant import (
            reset_tenant_key as _reset_tenant,
            set_tenant_key as _set_tenant,
            tenant_key_from_schema as _schema_to_key,
        )

        tenant_key = _schema_to_key(final_tenant_schema)
        token = _set_tenant(tenant_key)
        try:
            with _t_session() as tsession:
                user = User(
                    id=final_account_id,
                    username=username,
                    display_name=user_info.name,
                )
                tsession.add(user)
                tsession.commit()
        finally:
            _reset_tenant(token)

    # Redirect with a short-lived one-time code (NOT the real tokens), so
    # long-lived credentials never appear in the URL / logs / history. The
    # frontend immediately exchanges this code via POST /oauth/exchange.
    # ?new=1 signals the frontend to show the ToS interstitial for new accounts.
    handoff_code = create_oauth_handoff_token(final_account_id)
    frontend_url = f"{site_url}/oauth/callback"
    new_param = "&new=1" if was_new_account else ""
    return RedirectResponse(
        url=f"{frontend_url}?code={handoff_code}{new_param}",
        status_code=302,
    )


class OAuthExchangeRequest(BaseModel):
    code: str


# nosemgrep: missing-auth-dependency (public OAuth exchange endpoint)
@router.post(
    "/oauth/exchange",
    summary="Exchange a one-time OAuth handoff code for JWT tokens",
    response_model=TokenResponse,
)
@limiter.limit("10/minute")
async def oauth_exchange(
    request: Request,
    body: OAuthExchangeRequest,
) -> TokenResponse:
    """Exchange the short-lived OAuth handoff code for real tokens."""
    payload = decode_token(body.code, expected_type="oauth_handoff")
    if payload is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired OAuth code",
        )

    account_id = int(payload["sub"])
    with public_session_scope() as session:
        account = session.query(Account).filter(
            Account.id == account_id
        ).first()
        if account is None or not account.is_active:
            raise HTTPException(
                status_code=401,
                detail="Account not found or disabled",
            )

        token_version = account.token_version or 0
        access_token = create_access_token(
            account.id, account.tenant_schema, token_version
        )
        refresh_token = create_refresh_token(account.id, token_version)
        tenant_schema = account.tenant_schema

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        tenant_key=tenant_schema,
    )


# ── Twitch OAuth ────────────────────────────────────────────────────


# nosemgrep: missing-auth-dependency (public Twitch OAuth login endpoint)
@router.get(
    "/oauth/twitch/login",
    summary="Initiate Twitch OAuth login",
)
async def twitch_oauth_login() -> RedirectResponse:
    """Redirect the user to the Twitch OAuth consent screen."""
    site_url = os.environ.get(
        "AIRUNNER_SITE_URL",
        "http://localhost:5173",
    ).strip().rstrip("/")

    auth_url = get_twitch_auth_url()
    if auth_url is None:
        return RedirectResponse(
            url=f"{site_url}/login?error=twitch_oauth_not_configured",
            status_code=302,
        )
    return RedirectResponse(url=auth_url, status_code=302)


# nosemgrep: missing-auth-dependency (public Twitch OAuth callback endpoint)
@router.get(
    "/oauth/twitch/callback",
    summary="Handle Twitch OAuth callback",
)
async def twitch_oauth_callback(
    request: Request,
    code: str,
    state: str,
) -> RedirectResponse:
    """Handle the OAuth callback from Twitch.

    On success, redirects to ``{SITE_URL}/oauth/callback`` with
    access/refresh tokens as query parameters.  On failure, redirects
    to ``{SITE_URL}/login?error=...``.
    """
    from airunner_services.data.tenant import tenant_schema_for_key

    site_url = os.environ.get(
        "AIRUNNER_SITE_URL",
        "http://localhost:5173",
    ).strip().rstrip("/")

    # Validate CSRF state
    if not consume_twitch_state(state):
        return RedirectResponse(
            url=f"{site_url}/login?error=invalid_oauth_state",
            status_code=302,
        )

    # Exchange code for user info
    user_info = await exchange_twitch_code(code)
    if user_info is None:
        return RedirectResponse(
            url=f"{site_url}/login?error=twitch_oauth_failed",
            status_code=302,
        )

    was_new_account = False

    with public_session_scope() as session:
        # Look up by twitch_id first
        account = session.query(Account).filter(
            Account.twitch_id == user_info.twitch_id
        ).first()

        if account is None:
            # Look up by email
            account = session.query(Account).filter(
                Account.email == user_info.email
            ).first()

            if account is not None:
                # Existing account with this email but different provider
                if (
                    account.auth_provider == ModelService.LOCAL.value
                    and account.password_hash is not None
                ):
                    return RedirectResponse(
                        url=(
                            f"{site_url}/login?"
                            f"{urlencode({
                                'error': 'email_exists',
                                'detail': (
                                    'An account with this email already '
                                    'exists. Sign in with your password '
                                    'instead, then link Twitch in settings.'
                                ),
                            })}"
                        ),
                        status_code=302,
                    )

                # Account exists with same email — link twitch_id
                account.twitch_id = user_info.twitch_id
                account.auth_provider = "twitch"
                session.add(account)
                session.flush()
            else:
                # Block new Twitch OAuth accounts when invite codes active
                _required_code = os.environ.get(
                    _INVITE_ENV, "",
                ).strip()
                if _required_code:
                    return RedirectResponse(
                        url=(
                            f"{site_url}/login?"
                            f"{urlencode({'error': 'invite_required'})}"
                        ),
                        status_code=302,
                    )
                # Create new account via Twitch OAuth
                was_new_account = True

                # Auto-generate random username (internal only).
                username = f"user_{uuid.uuid4().hex[:8]}"

                # Pure UUID tenant key — no username embedded.
                raw_key = uuid.uuid4().hex
                tenant_schema = tenant_schema_for_key(raw_key)

                now = datetime.datetime.now(datetime.timezone.utc)
                account = Account(
                    email=user_info.email,
                    username=username,
                    password_hash=None,
                    is_verified=True,
                    twitch_id=user_info.twitch_id,
                    auth_provider="twitch",
                    tenant_schema=tenant_schema,
                    created_at=now,
                )
                session.add(account)
                session.flush()

        # Update last login
        account.last_login = datetime.datetime.now(datetime.timezone.utc)
        session.add(account)
        session.flush()

        final_account_id = account.id
        final_tenant_schema = account.tenant_schema

    # Provision tenant for newly created accounts
    if was_new_account:
        _provision_tenant(final_tenant_schema)

        # Pre-fill display_name from Twitch profile so the onboarding
        # NameStep is skippable (matching Steam/Bluesky behaviour).
        from airunner_services.database.models.user import (
            User,
        )
        from airunner_services.database.session import (
            session_scope as _t_session,
        )
        from airunner_services.data.tenant import (
            reset_tenant_key as _reset_tenant,
            set_tenant_key as _set_tenant,
            tenant_key_from_schema as _schema_to_key,
        )

        tenant_key = _schema_to_key(final_tenant_schema)
        token = _set_tenant(tenant_key)
        try:
            with _t_session() as tsession:
                user = User(
                    id=final_account_id,
                    username=username,
                    display_name=user_info.display_name,
                )
                tsession.add(user)
                tsession.commit()
        finally:
            _reset_tenant(token)

    # Redirect with handoff code
    handoff_code = create_oauth_handoff_token(final_account_id)
    frontend_url = f"{site_url}/oauth/callback"
    new_param = "&new=1" if was_new_account else ""
    return RedirectResponse(
        url=f"{frontend_url}?code={handoff_code}{new_param}",
        status_code=302,
    )


# ── Include sub-routers ──────────────────────────────────────────

from .routes_admin import router as admin_router

router.include_router(admin_router)
