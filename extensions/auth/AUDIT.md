# Auth Extension — Audit & Account Management (2026-06-10)

This document records a review of the auth extension, the bugs found and
fixed, and how to administer accounts (the framework-free equivalent of
Django's `createsuperuser`). It exists so the next person doesn't have to
re-derive any of it.

---

## TL;DR

- **Accounts are created only via `POST /api/v1/auth/register`** (self-service)
  or the new **management CLI** (`extensions/auth/server/manage.py`). There is
  no web framework, so the CLI is the supported way to bootstrap an admin.
- The custom extension's **security posture is sound** (argon2id, login rate
  limiting, user-enumeration timing defense, short-lived JWTs with refresh +
  `token_version` revocation, per-tenant schema isolation). The problems were
  **operational**, not cryptographic.
- Three fixes landed (below): registration was crashing in multi-tenant mode,
  there was no admin tooling, and `is_superuser` was a dead column.

---

## Security review

What was checked in `extensions/auth/server/` and how it stands:

| Area | Finding |
|---|---|
| Password hashing | ✅ argon2id, OWASP-recommended cost params (`passwords.py`). |
| User enumeration | ✅ `dummy_verify()` burns equal CPU on missing/OAuth-only accounts so login timing doesn't leak which emails exist. |
| Brute force | ✅ `@limiter.limit("10/minute")` on login (slowapi). |
| Tokens | ✅ HS256 access (15 min) + refresh (7 d); `token_version` column invalidates all refresh tokens ("logout everywhere"). |
| Secret hygiene | ✅ `jwt.py` refuses the dev fallback secret in production. |
| Tenancy | ✅ schema-per-user isolation; `accounts` is the only cross-tenant table, accessed solely via `public_session_scope()`. |
| Authorization | ⚠️→✅ `is_superuser` existed but was never enforced; now wired (see fix 3). |
| Email verification | ⚠️ `is_verified` is set but **not enforced on login** — unverified users can log in. This is a product decision; enforce in `login()` if you want a hard gate. |

No credential leakage, SQL injection, or token-forgery issues were found in
the reviewed paths.

---

## Fixes applied (2026-06-10)

### 1. Registration 500 in multi-tenant mode (tenant schemas were empty)

**Symptom:** `POST /auth/register` returned `{"error":"Internal server error"}`
(500). The account row was still committed (so login worked), but the user's
tenant schema was never populated — **every `tenant_*` schema had 0 tables.**

**Root cause:** `register()` → `_provision_tenant()` → `setup_database(tenant_url)`
runs the full Alembic migration set against the new tenant schema. Alembic
traversed the auth revision **twice** in a single `upgrade("heads")` pass (the
core and extension migration roots are disconnected — two bases sharing one
upgrade), so `001_create_accounts`'s `op.create_table("accounts")` ran a second
time and raised `DuplicateTable`, aborting the whole upgrade. Net effect: no
tenant tables, 500 to the client.

**Fix:** made the auth migrations **idempotent**. New helper
`server/migration_utils.py` (`has_table` / `has_column`); `001`/`002`/`003` now
short-circuit if their target already exists, so a re-apply is a no-op instead
of a crash. After the fix, provisioning creates the full ~55-table tenant
schema and register returns 200.

> Note: a tenant schema still gets a (harmless, unused) copy of `accounts`
> because `001` runs once in the tenant search_path. The app only ever reads
> `accounts` from `public` via `public_session_scope()`. Removing the per-tenant
> copy would require public-vs-tenant migration separation in core
> `setup_database` — out of scope for this fix and not a correctness issue.

Files: `server/migration_utils.py` (new), `server/migrations/versions/001_*.py`,
`002_*.py`, `003_*.py`.

### 2. No account-management tooling → new CLI

**`extensions/auth/server/manage.py`** — the `createsuperuser` equivalent. Run
inside the server container; reuses the same hashing + tenant-provisioning code
as the HTTP register path, so CLI accounts are identical to registered ones.

```bash
# create the first admin
./scripts/docker.sh auth create-user \
    --email you@example.com --username admin --password 'secret123' --superuser

./scripts/docker.sh auth list
./scripts/docker.sh auth promote --email someone@example.com          # grant
./scripts/docker.sh auth promote --email someone@example.com --demote # revoke
./scripts/docker.sh auth repair-tenant --email old@example.com  # re-provision
./scripts/docker.sh auth delete --email junk@example.com --yes
```

`create-user` flags: `--superuser`, `--unverified`, `--no-tenant`. Password is
prompted securely if `--password` is omitted. The `auth` subcommand was added
to `scripts/docker.sh`. Outside Docker:
`python -m extensions.auth.server.manage <cmd>`.

### 3. `is_superuser` wired into real authorization

**`server/dependencies.py`** gained `require_superuser` (authenticates via
`require_auth`, loads the account from `public.accounts`, enforces
`is_superuser`; 401 unauth / 403 non-super). It guards the first admin route,
**`GET /api/v1/auth/admin/accounts`** (lists all accounts) — both a useful admin
read and the canonical example for protecting future admin endpoints.

Verified: unauthenticated → 401, normal user → 403, superuser → 200.

---

## Architecture-direction note

We evaluated migrating auth to Django or a full FastAPI auth framework. **Keep
the custom extension.** The app is a FastAPI daemon with bespoke
schema-per-user multitenancy; Django would be a backend-wide rewrite fighting
its ORM/User assumptions, and `fastapi-users` has no native schema-per-tenant
(you'd rewrite provisioning anyway). The extension already implements the
hard, security-sensitive parts correctly — the gaps were the operational ones
closed above. See the conversation/commit history for the full rationale.

---

## Related

- Multi-tenant model & security properties: [ARCHITECTURE.md](ARCHITECTURE.md)
- Env vars, email/OAuth, migrations: [SETUP.md](SETUP.md)
- Docker login troubleshooting (separate boot/crash-loop bug fixed the same
  day): see the open-core repo `docker/README.md` and `docker/entrypoint.sh`.
