"""Reusable two-tenant adversarial test fixture for cross-tenant
isolation testing.

Creates two real tenant schemas, seeds representative data into each,
and provides assertion helpers for verifying that tenant B cannot
access tenant A's resources.  Designed to be imported by
``test_tenant_isolation_matrix.py``.

Follows the real-DB pattern from ``test_migration_idempotency.py``:
requires ``AIRUNNER_TEST_DATABASE_URL`` (or falls back to
``AIRUNNER_DATABASE_URL``) and skips with a clear reason when neither
is configured.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from airunner_services.data.tenant import (
    reset_tenant_key,
    set_tenant_key,
    tenant_schema_for_key,
)
from airunner_services.database.db.engine import create_configured_engine
from airunner_services.database.session import (
    _tenant_db_url,
    reset_engine,
    session_scope,
)


# ---------------------------------------------------------------------------
# Tenant key helpers
# ---------------------------------------------------------------------------


def _fresh_tenant_key(prefix: str = "isotest") -> str:
    """Return a unique tenant key for a test schema."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Schema lifecycle
# ---------------------------------------------------------------------------


def _drop_schema(tenant_key: str) -> None:
    """Drop the scratch tenant schema identified by *tenant_key*."""
    schema = tenant_schema_for_key(tenant_key)
    db_url = os.environ.get("AIRUNNER_DATABASE_URL", "")
    if not db_url:
        return
    tenant_url = _tenant_db_url(db_url, schema)
    engine = create_configured_engine(tenant_url)
    try:
        from sqlalchemy import text

        with engine.begin() as conn:
            conn.execute(
                text(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            )
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Seeded data container
# ---------------------------------------------------------------------------


@dataclass
class TenantData:
    """IDs and keys for one tenant's seeded resources."""

    tenant_key: str
    account_id: int
    chatbot_id: int
    chatbot_name: str = ""
    gem_balance: int = 0
    item_id: int = 0
    card_id: int = 0
    room_id: int = 0
    conv_id: int = 0
    document_id: int = 0
    doc_id: str = ""
    chunk_id: int = 0
    calendar_event_id: int = 0
    steam_connection_id: int = 0
    steam_id: str = ""
    itch_connection_id: int = 0
    itch_user_id: str = ""
    twitch_connection_id: int = 0
    twitch_id: str = ""
    email_account_id: int = 0
    email_address: str = ""


# ---------------------------------------------------------------------------
# TestClient factory — builds a FastAPI app with a tenant-injecting
# middleware so route handlers that call ``require_auth`` (reading
# ``request.state.account_id``) and ``session_scope()`` (reading the
# tenant contextvar) resolve to the specified tenant.
# ---------------------------------------------------------------------------


def make_tenant_client(
    router: Any,
    router_prefix: str,
    *,
    account_id: int = 42,
    tenant_key: str,
) -> TestClient:
    """Build a ``TestClient`` that authenticates as *account_id* in
    *tenant_key*'s schema.

    Every request passes ``require_auth`` (the middleware sets
    ``request.state.account_id``) and the tenant contextvar is set so
    ``session_scope()`` resolves to the correct schema.
    """
    app = FastAPI()

    @app.middleware("http")
    async def _inject_tenant(request, call_next):
        request.state.account_id = account_id
        token = set_tenant_key(tenant_key)
        try:
            return await call_next(request)
        finally:
            reset_tenant_key(token)

    app.include_router(router, prefix=router_prefix)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Cross-tenant assertion helper
# ---------------------------------------------------------------------------


def assert_cross_tenant_denied(
    client: TestClient,
    method: str,
    path: str,
    *,
    tenant_a_resource_label: str = "",
    expected_statuses: tuple[int, ...] = (401, 403, 404),
    expect_empty_body: bool = False,
    **request_kwargs: Any,
) -> None:
    """Assert that tenant B cannot access tenant A's resource.

    Calls *method* *path* via *client* (authenticated as tenant B) and
    verifies that the response does NOT return tenant A's data.  The
    assertion style mirrors the pattern established in round-6/7
    security tests (``test_object_storage_tenant_isolation.py`` and
    ``test_economy_trades_auth.py``).

    Args:
        client: ``TestClient`` authenticated as tenant B.
        method: HTTP method (``GET``, ``POST``, ``PUT``, ``DELETE``).
        path: Request path (e.g. ``/economy/gems/balance``).
        tenant_a_resource_label: Human-readable label for assertion
            messages.
        expected_statuses: Acceptable denial status codes.
        expect_empty_body: When ``True``, the response body must be
            an empty list or equivalent.
        **request_kwargs: Passed to the ``TestClient`` method call
            (e.g. ``json=...`` for POST bodies).
    """
    http_method = getattr(client, method.lower(), None)
    if http_method is None:
        raise ValueError(f"Unknown HTTP method: {method}")

    label = tenant_a_resource_label or path

    resp = http_method(path, **request_kwargs)
    assert resp.status_code in expected_statuses, (
        f"Expected denial ({expected_statuses}) for {label}, "
        f"got {resp.status_code}"
    )

    if expect_empty_body:
        body = resp.json() if resp.content else {}
        if isinstance(body, list):
            assert len(body) == 0, (
                f"Expected empty list for {label}, got {len(body)} items"
            )
        elif isinstance(body, dict):
            assert body == {} or body == {"detail": body.get("detail")}, (
                f"Expected empty/minimal dict for {label}, got {body}"
            )


# ---------------------------------------------------------------------------
# Real-DB fixture: two tenants with seeded data
# ---------------------------------------------------------------------------


@dataclass
class TwoTenants:
    """Two tenant schemas with seeded resources."""

    tenant_a: TenantData
    tenant_b: TenantData
    db_url: str


@pytest.fixture()
def two_tenants(monkeypatch: pytest.MonkeyPatch) -> Generator[
    TwoTenants, None, None
]:
    """Create two tenant schemas, seed representative data into each,
    and tear both down after the test.

    Each tenant gets a ``User`` row (for gem-balance tests) and a
    ``Chatbot`` row.  The returned ``TwoTenants`` carries the tenant
    keys and created IDs so test bodies can target specific resources.

    Requires ``AIRUNNER_TEST_DATABASE_URL`` or falls back to
    ``AIRUNNER_DATABASE_URL``; skips when neither is a PostgreSQL URL.
    """
    db_url = os.environ.get(
        "AIRUNNER_TEST_DATABASE_URL",
        os.environ.get("AIRUNNER_DATABASE_URL"),
    )
    if not db_url:
        pytest.skip(
            "No test database configured "
            "(AIRUNNER_TEST_DATABASE_URL)"
        )
    if not db_url.startswith("postgres"):
        pytest.skip(
            "Tenant-isolation matrix tests require PostgreSQL"
        )
    monkeypatch.setenv("AIRUNNER_DATABASE_URL", db_url)
    monkeypatch.setenv("AIRUNNER_DB_TENANCY", "multi")
    monkeypatch.setenv("AIRUNNER_DISABLE_DB_SETUP_CACHE", "1")
    reset_engine()
    key_a = _fresh_tenant_key("isotest_a")
    key_b = _fresh_tenant_key("isotest_b")

    # ── Seed tenant A ──────────────────────────────────────────
    from airunner_services.data.tenant import tenant_scope

    try:
        with tenant_scope(key_a):
            with session_scope() as session:
                # Seed extra throwaway chatbots/events so tenant A's
                # "real" IDs are higher than tenant B's.  Prevents
                # false-pass cross-tenant tests when both schemas
                # happen to get the same sequence value.
                _seed_tenant(
                    session, key_a, gems=100,
                    extra_chatbots=2, extra_events=2,
                )
    except Exception as exc:
        reset_engine()
        _drop_schema(key_a)
        _drop_schema(key_b)
        pytest.skip(f"Database setup failed (tenant A): {exc}")

    # ── Seed tenant B ──────────────────────────────────────────
    try:
        with tenant_scope(key_b):
            with session_scope() as session:
                _seed_tenant(
                    session, key_b, gems=250, extra_chatbots=0,
                )
    except Exception as exc:
        reset_engine()
        _drop_schema(key_a)
        _drop_schema(key_b)
        pytest.skip(f"Database setup failed (tenant B): {exc}")

    # ── Read back the IDs we just created ──────────────────────
    data_a = _read_tenant_data(key_a, gem_balance=100)
    data_b = _read_tenant_data(key_b, gem_balance=250)

    yield TwoTenants(
        tenant_a=data_a,
        tenant_b=data_b,
        db_url=db_url,
    )

    # ── Tear down ──────────────────────────────────────────────
    reset_engine()
    _drop_schema(key_a)
    _drop_schema(key_b)


# ---------------------------------------------------------------------------
# Internal seeding helpers
# ---------------------------------------------------------------------------


def _seed_tenant(
    session: Any,
    tenant_key: str,
    *,
    gems: int = 100,
    extra_chatbots: int = 0,
    extra_events: int = 0,
) -> None:
    """Insert representative rows into *session*.

    Uses raw SQL INSERT so we do not depend on model-level
    ``objects.create`` behaviour (which may vary across subsystems).

    Args:
        session: Active SQLAlchemy session bound to the tenant schema.
        tenant_key: Tenant identifier used for generated names.
        gems: Starting gem balance for the user row.
        extra_chatbots: Number of throwaway chatbot rows to insert
            before the "real" one (used to force divergent IDs across
            tenants so ID-collision false positives are impossible).
        extra_events: Same, but for calendar_events rows.
    """
    from sqlalchemy import text

    # The `users` table has no `email` column (see
    # database/models/user.py). daily_pulls_taken/paid_pulls_available/
    # streak_count are NOT NULL with only a Python-level ORM default
    # (no server_default), so raw SQL must supply them explicitly.
    user_row = session.execute(
        text(
            "INSERT INTO users "
            "(username, gems, daily_pulls_taken, "
            "paid_pulls_available, streak_count, deleted, created_at) "
            "VALUES (:username, :gems, 0, 0, 0, false, NOW()) "
            "RETURNING id"
        ),
        {
            "username": f"user_{tenant_key[:8]}",
            "gems": gems,
        },
    ).fetchone()
    user_id = int(user_row[0])
    # Chatbot NOT NULL columns with only a Python-level ORM default
    # (no server_default) -- raw SQL must supply them explicitly.
    chatbot_insert = text(
        "INSERT INTO chatbots "
        "(name, species, allow_narrative_text, knowledge_mode, "
        "language_proficiency, is_online, has_blocked_user, "
        "blocked_by_user, is_deceased, is_system_bot, "
        "omnipotent_knowledge, deleted, created_at) "
        "VALUES (:name, :species, false, 'omniscient', 'fluent', "
        "true, false, false, false, false, false, false, NOW())"
    )

    # Insert extra throwaway chatbots first so the "real" one gets
    # a higher ID — prevents false-pass cross-tenant tests when
    # both schemas happen to assign the same sequence value.
    for i in range(extra_chatbots):
        session.execute(
            chatbot_insert,
            {"name": f"_throwaway_{i}", "species": "human"},
        )
    session.execute(
        chatbot_insert,
        {"name": f"bot_{tenant_key[:8]}", "species": "human"},
    )

    # Calendar event -- all_day/is_recurring_reminder/deleted are
    # NOT NULL with only a Python-level ORM default.
    event_insert = text(
        "INSERT INTO calendar_events "
        "(user_id, title, starts_at, all_day, "
        "is_recurring_reminder, deleted, created_at) "
        "VALUES (:user_id, :title, NOW(), false, false, "
        "false, NOW())"
    )
    for i in range(extra_events):
        session.execute(
            event_insert,
            {"user_id": user_id, "title": f"_throwaway_event_{i}"},
        )
    session.execute(
        event_insert,
        {"user_id": user_id, "title": f"event_{tenant_key[:8]}"},
    )
    # Integration connection rows — seeded with tenant_key-derived
    # identifiers so cross-tenant content-check tests can distinguish
    # tenant A's data from tenant B's when the colliding account_id
    # causes the auth check to pass through to the DB query.
    session.execute(
        text(
            "INSERT INTO steam_connections "
            "(account_id, steam_id, deleted, created_at) "
            "VALUES (:account_id, :steam_id, false, NOW())"
        ),
        {
            "account_id": user_id,
            "steam_id": f"steam_{tenant_key[:16]}",
        },
    )
    session.execute(
        text(
            "INSERT INTO itch_connections "
            "(account_id, itch_user_id, deleted, created_at) "
            "VALUES (:account_id, :itch_user_id, false, NOW())"
        ),
        {
            "account_id": user_id,
            "itch_user_id": hash(tenant_key) % 10_000_000,
        },
    )
    session.execute(
        text(
            "INSERT INTO twitch_connections "
            "(account_id, twitch_id, deleted, created_at) "
            "VALUES (:account_id, :twitch_id, false, NOW())"
        ),
        {
            "account_id": user_id,
            "twitch_id": f"twitch_{tenant_key[:16]}",
        },
    )
    # EmailAccount — credential_ciphertext expects encrypted data,
    # but with no DEK/global key in test env it stores plaintext.
    session.execute(
        text(
            "INSERT INTO email_accounts "
            "(user_id, provider, email_address, credential_ciphertext, "
            "status, deleted, created_at) "
            "VALUES (:user_id, 'fastmail', :email, :token, "
            "'connected', false, NOW())"
        ),
        {
            "user_id": user_id,
            "email": f"{tenant_key[:12]}@example.com",
            "token": f"token_{tenant_key[:8]}",
        },
    )
    # Document — knowledge-base document with a meaningful path.
    doc_hash = f"dochtml_{tenant_key[:16]}"
    doc_row = session.execute(
        text(
            "INSERT INTO documents "
            "(path, active, indexed, chatbot_id, file_hash, deleted, "
            "created_at) "
            "VALUES (:path, true, true, :chatbot_id, :hash, "
            "false, NOW()) "
            "RETURNING id"
        ),
        {
            "path": f"/kb/{tenant_key[:12]}.txt",
            "chatbot_id": user_id,
            "hash": doc_hash,
        },
    ).fetchone()
    doc_db_id = int(doc_row[0])
    # DocumentChunk — with a realistic embedding so pgvector
    # similarity searches can locate it.  The embedding is a random
    # unit vector; the content is a distinct per-tenant label so
    # cross-tenant leak detection is trivial.
    import random as _random
    import math as _math
    from airunner_services.database.models.document_chunk import (
        EMBEDDING_DIM,
    )
    vec = [_random.gauss(0, 1) for _ in range(EMBEDDING_DIM)]
    norm = _math.sqrt(sum(v * v for v in vec))
    unit = [v / norm for v in vec]
    # Content carries the tenant key so cross-tenant leak detection
    # is discriminating: tenant B's schema must never contain a chunk
    # whose content includes tenant A's identifier.
    chunk_content = (
        f"SHARED_SECRET_CROSS_TENANT_LEAK_{tenant_key[:16]}"
    )
    session.execute(
        text(
            "INSERT INTO document_chunks "
            "(document_id, doc_id, chunk_index, content, "
            "chunk_metadata, embedding, deleted, created_at) "
            "VALUES (:doc_id, :hash, 0, :content, "
            "'{}'::jsonb, :embedding, false, NOW())"
        ),
        {
            "doc_id": doc_db_id,
            "hash": doc_hash,
            "content": chunk_content,
            "embedding": unit,
        },
    )
    session.flush()


def _read_tenant_data(
    tenant_key: str, *, gem_balance: int = 0,
) -> TenantData:
    """Read back the seeded IDs and names for one tenant."""
    from airunner_services.data.tenant import tenant_scope

    with tenant_scope(tenant_key):
        with session_scope() as session:
            from sqlalchemy import text

            user_row = session.execute(
                text(
                    "SELECT id, gems FROM users ORDER BY id LIMIT 1"
                )
            ).fetchone()
            bot_row = session.execute(
                text(
                    "SELECT id, name FROM chatbots "
                    "ORDER BY id DESC LIMIT 1"
                )
            ).fetchone()
            event_row = session.execute(
                text(
                    "SELECT id FROM calendar_events "
                    "ORDER BY id DESC LIMIT 1"
                )
            ).fetchone()
            # Read account_id first so integration queries can use it.
            uid = int(user_row[0]) if user_row else 0
            steam_row = session.execute(
                text(
                    "SELECT id, steam_id FROM steam_connections "
                    "WHERE account_id = :aid"
                ),
                {"aid": uid},
            ).fetchone()
            itch_row = session.execute(
                text(
                    "SELECT id, itch_user_id FROM itch_connections "
                    "WHERE account_id = :aid"
                ),
                {"aid": uid},
            ).fetchone()
            twitch_row = session.execute(
                text(
                    "SELECT id, twitch_id FROM twitch_connections "
                    "WHERE account_id = :aid"
                ),
                {"aid": uid},
            ).fetchone()
            email_row = session.execute(
                text(
                    "SELECT id, email_address FROM email_accounts "
                    "WHERE user_id = :uid AND deleted = false"
                ),
                {"uid": uid},
            ).fetchone()
            doc_row = session.execute(
                text(
                    "SELECT id, file_hash FROM documents "
                    "ORDER BY id DESC LIMIT 1"
                )
            ).fetchone()
            chunk_row = session.execute(
                text(
                    "SELECT id FROM document_chunks "
                    "ORDER BY id DESC LIMIT 1"
                )
            ).fetchone()

    account_id = int(user_row[0]) if user_row else 0
    read_gems = int(user_row[1]) if user_row else gem_balance
    chatbot_id = int(bot_row[0]) if bot_row else 0
    chatbot_name = str(bot_row[1]) if bot_row else ""
    calendar_event_id = int(event_row[0]) if event_row else 0
    steam_connection_id = int(steam_row[0]) if steam_row else 0
    steam_id = str(steam_row[1]) if steam_row else ""
    itch_connection_id = int(itch_row[0]) if itch_row else 0
    itch_user_id = str(itch_row[1]) if itch_row else ""
    twitch_connection_id = int(twitch_row[0]) if twitch_row else 0
    twitch_id = str(twitch_row[1]) if twitch_row else ""
    email_account_id = int(email_row[0]) if email_row else 0
    email_address = str(email_row[1]) if email_row else ""
    document_id = int(doc_row[0]) if doc_row else 0
    doc_id = str(doc_row[1]) if doc_row else ""
    chunk_id = int(chunk_row[0]) if chunk_row else 0

    return TenantData(
        tenant_key=tenant_key,
        account_id=account_id,
        chatbot_id=chatbot_id,
        chatbot_name=chatbot_name,
        gem_balance=read_gems,
        document_id=document_id,
        doc_id=doc_id,
        chunk_id=chunk_id,
        calendar_event_id=calendar_event_id,
        steam_connection_id=steam_connection_id,
        steam_id=steam_id,
        itch_connection_id=itch_connection_id,
        itch_user_id=itch_user_id,
        twitch_connection_id=twitch_connection_id,
        twitch_id=twitch_id,
        email_account_id=email_account_id,
        email_address=email_address,
    )


# ---------------------------------------------------------------------------
# Convenience: build a cross-tenant test client
# ---------------------------------------------------------------------------


def make_cross_tenant_client(
    router: Any,
    prefix: str,
    tenant_b: TenantData,
) -> TestClient:
    """Build a ``TestClient`` authenticated as tenant B for
    cross-tenant attack testing.

    The returned client makes requests that resolve to tenant B's
    schema.  Test bodies use it to attempt access to tenant A's
    resource IDs.
    """
    return make_tenant_client(
        router,
        prefix,
        account_id=tenant_b.account_id,
        tenant_key=tenant_b.tenant_key,
    )
