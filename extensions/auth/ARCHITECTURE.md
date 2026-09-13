# Auth Extension — Multi-Tenant Architecture

This document describes how the auth extension keeps each user's data
isolated from every other user's, how a request is routed to the correct
data namespace, and the security properties (and limitations) of that
design.

---

## Overview

The system uses **schema-per-tenant** isolation on PostgreSQL:

- There is **one shared `accounts` table** in the Postgres `public`
  schema. It holds credentials and the pointer to each user's namespace.
- Every other table (conversations, settings, etc.) is **duplicated into
  a per-user schema** named `tenant_<key>`.
- A signed JWT carries the user's schema name. On each request the auth
  middleware establishes that schema as the active namespace, and all ORM
  queries for that request operate **only** inside it via the Postgres
  `search_path`.

This is the namespace model you described, and it exists in the current
architecture. The pieces:

| Concern | Where |
|---|---|
| Shared account store | `accounts` table, `__public_schema__ = True` (`server/models.py`) |
| Namespace identifier | `accounts.tenant_schema` column + JWT `tenant` claim |
| Per-request namespace context | `auth/server/middleware.py` → `set_tenant_key()` |
| Namespace → `search_path` | `airunner_services/database/session.py` (`session_scope`) |
| Public (cross-tenant) access | `public_session_scope()` — used only for `accounts` |

---

## Lifecycle

### 1. Registration / first OAuth login

```
raw_key      = "<uuid12>_<username>"          # e.g. "<key>_joe"
tenant_schema = tenant_schema_for_key(raw_key) # e.g. "tenant_<key>_joe"
```

1. A row is inserted into the **public** `accounts` table with
   `tenant_schema` stored on it.
2. `_provision_tenant()` runs:
   - PostgreSQL: `CREATE SCHEMA IF NOT EXISTS tenant_...` then
     `setup_database(tenant_url)` runs **all** migrations (core + auth)
     inside that schema, giving the user a fresh, private copy of every
     table.
   - SQLite (local/dev): single-user, no per-user schema — migrations run
     against the one database file.

### 2. Login

The password is verified against the **public** `accounts` table
(`public_session_scope`), then a JWT is issued containing:

```json
{ "sub": "<account_id>", "tenant": "tenant_<key>_joe", "ver": 0, "type": "access" }
```

(Google OAuth login is the same, except the callback hands the browser a
60-second one-time `oauth_handoff` code which the frontend exchanges via
`POST /oauth/exchange` for these tokens — see "Hardening" below.)

### 3. Authenticated request

1. `auth_middleware` decodes the JWT and recovers the **raw** tenant key
   from the schema name via `tenant_key_from_schema()`, then calls
   `set_tenant_key(raw_key)` (a `ContextVar`).
2. When request code opens `session_scope()`, the session layer computes
   `tenant_schema_for_key(get_tenant_key())` and issues
   `SET LOCAL search_path TO tenant_...`.
3. Every query in that transaction resolves table names inside the user's
   schema. At commit/rollback the `SET LOCAL` is discarded, so the pooled
   connection carries **no** tenant state back to the pool.
4. The middleware resets the `ContextVar` in a `finally` block so the
   namespace never leaks to the next request on the same worker.

> **Critical invariant:** `set_tenant_key()` takes the *raw* key; the
> session layer re-applies the `tenant_` prefix. Passing an
> already-prefixed schema double-prefixes it
> (`tenant_tenant_...`) and silently points the request at a
> non-existent schema. `tenant_key_from_schema()` exists to enforce this
> at the JWT boundary. (This was a real bug — see history.)

---

## Why this is sound

- **Authenticity:** the namespace is carried in a *signed* JWT
  (`AIRUNNER_JWT_SECRET`). A client cannot choose another user's schema
  without forging the signature.
- **Per-request scoping:** `SET LOCAL` is transaction-scoped, so tenant
  context cannot survive on a connection returned to the shared pool.
- **No leakage between requests:** the `ContextVar` is set and reset
  per request; nothing persists on the worker between requests.
- **Injection-safe schema names:** schema names are always produced by
  `tenant_schema_for_key()`, which reduces input to `[a-z0-9_]`. That
  sanitisation is the *only* thing protecting the
  `SET LOCAL search_path TO {schema}` / `CREATE SCHEMA {schema}`
  string interpolation — never bypass it by interpolating an unsanitised
  value into those statements.

---

## Hardening that is implemented

- **Stateless OAuth CSRF state.** The `state` parameter is a signed,
  short-lived token (`oauth_state`, TTL `AIRUNNER_OAUTH_STATE_TTL`), not
  in-process memory. It is multi-worker safe and self-expiring.
- **No long-lived tokens in URLs (OAuth).** The Google callback redirects
  with a single, short-lived one-time code (`oauth_handoff`, TTL
  `AIRUNNER_OAUTH_HANDOFF_TTL`, default 60 s). The browser exchanges it
  via `POST /oauth/exchange` for the real tokens, so the 7-day refresh
  token never lands in a URL, log, or `Referer`.
- **Token revocation / logout.** Each account has a `token_version`;
  access/refresh tokens carry it as a `ver` claim. `POST /logout` bumps
  it, which invalidates every outstanding refresh token
  ("sign out everywhere"). Refresh validates `ver` against the DB.
- **Constant-time login.** When the email is unknown (or is an OAuth-only
  account with no password) the login path still runs an Argon2 verify
  against a dummy hash, so response timing doesn't reveal which emails
  are registered.
- **Fail-fast DB policy.** With `AIRUNNER_REQUIRE_POSTGRES=1`, startup
  refuses to run on SQLite or in single-tenant mode — preventing a silent
  loss of isolation.

## Remaining limitations (by design — plan for these)

1. **Logical isolation, not physical.** All tenants share one database,
   one DB role, and one connection pool. Isolation is enforced by
   `search_path`, not by the database's permission system. A query that
   *fully-qualifies* another schema (`other_schema.table`), or a raw-SQL
   injection, would cross the tenant boundary. For stronger isolation
   consider per-tenant DB roles + `GRANT`/`REVOKE`, or PostgreSQL
   Row-Level Security.

2. **Core API-key middleware interaction.** The core server also installs
   `api_key_auth_middleware`. With the auth extension handling auth via
   JWT, remote (non-loopback) requests are rejected with `403` unless you
   set `AIRUNNER_API_KEY` *or* `AIRUNNER_INSECURE_NO_AUTH=1`. A JWT-only
   deployment uses the latter (the JWT middleware is the gate).

3. **Access tokens are valid until expiry.** `token_version` revocation
   is checked on **refresh** only — the hot per-request path stays
   stateless (no DB hit). A leaked *access* token therefore works until
   it expires; keep `AIRUNNER_JWT_ACCESS_TTL` short (default 15 min).

4. **WebSocket `?token=` query param.** Browsers can't set headers on WS
   upgrades, so the access token is still accepted via query string for
   those. Restrict access-log retention accordingly.

5. **Registration enumeration.** `register` returns `409` for an existing
   email/username (inherent to the unique constraint + good UX). The
   *login* timing side-channel is closed (see above); tighten register
   too if enumeration is a concern.

---

## Required configuration (PostgreSQL + multi-tenant — dev and prod)

Dev now mirrors production: **everything runs on PostgreSQL; nothing falls
back to SQLite.**

```bash
AIRUNNER_DATABASE_URL=postgresql://user:pass@host:5432/airunner
AIRUNNER_DATABASE_BACKEND=postgresql   # or set the URL above directly
AIRUNNER_DB_TENANCY=multi              # per-tenant schemas (default "single")
AIRUNNER_REQUIRE_POSTGRES=1            # fail fast on sqlite / single-tenant
AIRUNNER_INSECURE_NO_AUTH=1            # core api-key gate off; JWT is the gate
AIRUNNER_JWT_SECRET=<random 64-hex>   # python -c "import secrets; print(secrets.token_hex(32))"
# Prod only: AIRUNNER_DEPLOYMENT_MODE=production
# Optional: AIRUNNER_TENANT_SCHEMA_PREFIX=tenant_   (default)
```

The DB role must be allowed to `CREATE SCHEMA` (needed to provision new
tenants on registration).

> **Open-core note:** these are set via `.env` / environment, not in
> checked-in defaults. The bundled desktop app still defaults to SQLite,
> single-tenant; only deployments that opt in (via the env vars above)
> require PostgreSQL.
