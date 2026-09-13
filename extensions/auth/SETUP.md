# Auth Extension — Setup & Configuration

This document covers how to configure the auth extension's email verification
and Google OAuth features for **development** and **production**.

> The auth extension requires **PostgreSQL with multi-tenant mode**
> (`AIRUNNER_DB_TENANCY=multi`) — dev now mirrors production and does not
> use SQLite. See [ARCHITECTURE.md](ARCHITECTURE.md) for the namespace
> isolation model, security properties, and the full required config.

---

## Environment Variables

All settings are configured via environment variables prefixed with
`AIRUNNER_`.  Add them to your `.env` file at the airunner repo root.

| Variable | Default | Description |
|----------|---------|-------------|
| `AIRUNNER_JWT_SECRET` | `dev-jwt-secret-…` | JWT signing secret (MUST be random in production) |
| `AIRUNNER_JWT_ACCESS_TTL` | `900` | Access token lifetime in seconds (15 min) |
| `AIRUNNER_JWT_REFRESH_TTL` | `604800` | Refresh token lifetime in seconds (7 days) |
| `AIRUNNER_VERIFICATION_TOKEN_TTL` | `86400` | Email verification token lifetime in seconds (24h) |
| `AIRUNNER_OAUTH_STATE_TTL` | `600` | OAuth CSRF state token lifetime in seconds (10 min) |
| `AIRUNNER_OAUTH_HANDOFF_TTL` | `60` | OAuth one-time handoff code lifetime in seconds |
| `AIRUNNER_SITE_URL` | `http://localhost:5173` | Public-facing URL for verification links & OAuth redirects |
| `AIRUNNER_DATABASE_URL` | *(computed)* | Full DB URL; **required to be PostgreSQL** for the auth extension |
| `AIRUNNER_DB_TENANCY` | `single` | Set to `multi` for per-user schema isolation |
| `AIRUNNER_REQUIRE_POSTGRES` | `0` | Set to `1` to fail fast on SQLite / single-tenant |
| `AIRUNNER_INSECURE_NO_AUTH` | `0` | Set to `1` so JWT auth is the gate (disables core api-key gate) |
| `AIRUNNER_SMTP_HOST` | *(empty)* | SMTP server hostname |
| `AIRUNNER_SMTP_PORT` | `587` | SMTP server port |
| `AIRUNNER_SMTP_USER` | *(empty)* | SMTP username |
| `AIRUNNER_SMTP_PASSWORD` | *(empty)* | SMTP password |
| `AIRUNNER_SMTP_FROM` | `noreply@airunner.local` | From address on outgoing emails |
| `AIRUNNER_SMTP_USE_TLS` | `true` | Enable STARTTLS |
| `AIRUNNER_GOOGLE_CLIENT_ID` | *(empty)* | Google OAuth client ID |
| `AIRUNNER_GOOGLE_CLIENT_SECRET` | *(empty)* | Google OAuth client secret |

---

## Running Database Migrations

New migrations for the auth extension (e.g. `002_add_oauth_fields.py`) are
auto-discovered by the extension loader.  Run migrations with:

```bash
# From the airunner repo root
cd server
alembic upgrade head
```

This applies all pending migrations across both the core app and all loaded
extensions, including auth.

---

## Account Management (creating users & admins)

There is no Django-style `createsuperuser`; the equivalent is the management
CLI at `extensions/auth/server/manage.py`. Self-service registration
(`POST /api/v1/auth/register`) always creates a plain user, so use the CLI to
**bootstrap the first superuser**. It runs inside the server container and
reuses the same hashing + tenant-provisioning as registration.

```bash
# Create the first admin (Docker)
./scripts/docker.sh auth create-user \
    --email you@example.com --username admin --password 'secret123' --superuser

./scripts/docker.sh auth list                                   # list accounts
./scripts/docker.sh auth promote --email you@example.com         # grant super
./scripts/docker.sh auth promote --email you@example.com --demote # revoke
./scripts/docker.sh auth repair-tenant --email you@example.com    # re-provision
./scripts/docker.sh auth delete --email junk@example.com --yes
```

`create-user` flags: `--superuser`, `--unverified` (default is verified),
`--no-tenant` (account row only). Omit `--password` to be prompted securely.
Outside Docker: `python -m extensions.auth.server.manage <command>` (needs the
app's DB env).

Authorization for admin endpoints is enforced by `require_superuser`
(`server/dependencies.py`); the reference admin route is
`GET /api/v1/auth/admin/accounts`. See [AUDIT.md](AUDIT.md) for the full
review and the rationale behind the design.

---

## Email Verification — Development

In development, you should **not** send real emails.  Use a local SMTP
server that catches all outgoing messages for inspection.

### Option 1: Mailpit (recommended)

[Mailpit](https://github.com/axllent/mailpit) is a modern, lightweight email
testing tool with a built-in web UI.

**Install:**
```bash
# Linux (standalone binary)
curl -sL https://raw.githubusercontent.com/axllent/mailpit/develop/install.sh | bash

# macOS (Homebrew)
brew install mailpit
```

**Run:**
```bash
mailpit
```

This starts an SMTP server on `localhost:1025` and a web UI on
`localhost:8025`.  Emails sent through Mailpit never leave your machine.

**Configure `.env`:**
```env
AIRUNNER_SMTP_HOST=localhost
AIRUNNER_SMTP_PORT=1025
AIRUNNER_SMTP_USER=
AIRUNNER_SMTP_PASSWORD=
AIRUNNER_SMTP_USE_TLS=false
AIRUNNER_SMTP_FROM=noreply@airunner.local
AIRUNNER_SITE_URL=http://localhost:5173
```

Open http://localhost:8025 to view captured emails.

### Option 2: MailHog

[MailHog](https://github.com/mailhog/MailHog) is another popular alternative.

**Install:**
```bash
# Linux / macOS (download binary)
# or use Docker:
docker run -d -p 1025:1025 -p 8025:8025 mailhog/mailhog
```

**Configure `.env`:**
```env
AIRUNNER_SMTP_HOST=localhost
AIRUNNER_SMTP_PORT=1025
AIRUNNER_SMTP_USER=
AIRUNNER_SMTP_PASSWORD=
AIRUNNER_SMTP_USE_TLS=false
```

### Option 3: No SMTP (degraded mode)

If SMTP is not configured at all, the auth extension **still works** —
accounts are created successfully but remain unverified.  A log warning is
emitted on each skipped email.  For local testing you can verify accounts
directly in the database:

```bash
sqlite3 ~/.local/share/airunner/data/airunner.db
UPDATE accounts SET is_verified = 1 WHERE email = 'your@email.com';
.exit
```

---

## Email Verification — Production

In production, **do not run your own SMTP server**.  Use a transactional
email service to ensure deliverability and avoid spam filters.

### Option 1: SendGrid (recommended for small deployments)

1. Create a [SendGrid](https://sendgrid.com) account (free tier: 100 emails/day)
2. Create an API key (Settings → API Keys → Create API Key with "Mail Send" access)
3. Verify your sender identity (Settings → Sender Authentication)

**Configure `.env`:**
```env
AIRUNNER_SMTP_HOST=smtp.sendgrid.net
AIRUNNER_SMTP_PORT=587
AIRUNNER_SMTP_USER=apikey
AIRUNNER_SMTP_PASSWORD=SG.your_actual_api_key_here
AIRUNNER_SMTP_FROM=verified-sender@yourdomain.com
AIRUNNER_SMTP_USE_TLS=true
AIRUNNER_SITE_URL=https://app.yourdomain.com
```

### Option 2: Mailgun

1. Create a [Mailgun](https://mailgun.com) account
2. Set up a sending domain and get your SMTP credentials

**Configure `.env`:**
```env
AIRUNNER_SMTP_HOST=smtp.mailgun.org
AIRUNNER_SMTP_PORT=587
AIRUNNER_SMTP_USER=postmaster@mg.yourdomain.com
AIRUNNER_SMTP_PASSWORD=your_mailgun_smtp_password
AIRUNNER_SMTP_FROM=noreply@mg.yourdomain.com
AIRUNNER_SMTP_USE_TLS=true
AIRUNNER_SITE_URL=https://app.yourdomain.com
```

### Option 3: Postmark

1. Create a [Postmark](https://postmarkapp.com) account
2. Verify a sender signature and get your server token and SMTP credentials

**Configure `.env`:**
```env
AIRUNNER_SMTP_HOST=smtp.postmarkapp.com
AIRUNNER_SMTP_PORT=587
AIRUNNER_SMTP_USER=your_server_token
AIRUNNER_SMTP_PASSWORD=your_server_token
AIRUNNER_SMTP_FROM=noreply@yourdomain.com
AIRUNNER_SMTP_USE_TLS=true
AIRUNNER_SITE_URL=https://app.yourdomain.com
```

### Option 4: Fastmail SMTP (interim)

Interim stopgap while a dedicated transactional provider is being chosen.
Fastmail exposes plain SMTP and supports app-specific passwords, so no
third-party service is required.

1. Enable SMTP for your Fastmail account (Settings → Password &
   Security → App passwords)
2. Generate an **app password** — never use your account password

**Configure `.env`:**
```env
AIRUNNER_SMTP_HOST=smtp.fastmail.com
AIRUNNER_SMTP_PORT=587
AIRUNNER_SMTP_USER=you@fastmail.example
AIRUNNER_SMTP_PASSWORD=your_fastmail_app_password
AIRUNNER_SMTP_FROM=you@fastmail.example
AIRUNNER_SMTP_USE_TLS=true
```

> **Low volume only.** Fastmail enforces send-rate limits and is not
> designed for bulk or transactional email at scale.

### Option 5: AWS SES SMTP (future)

When volume outgrows the interim provider, AWS SES exposes SMTP at
`smtp.<region>.amazonaws.com` (e.g. `email.us-east-1.amazonaws.com`).
SES SMTP uses **SMTP-specific credentials** (generated in the SES
console) that are distinct from your regular AWS access keys.

Switching later is a **pure environment-variable change** — no code
change in `email.py`:
```env
AIRUNNER_SMTP_HOST=smtp.us-east-1.amazonaws.com
AIRUNNER_SMTP_PORT=587
AIRUNNER_SMTP_USER=your_ses_smtp_username
AIRUNNER_SMTP_PASSWORD=your_ses_smtp_password
AIRUNNER_SMTP_FROM=verified-sender@yourdomain.com
AIRUNNER_SMTP_USE_TLS=true
```

### Important production notes

- **Never** commit SMTP credentials to version control — use `.env` files or
  the runtime environment (e.g. container secrets, CI/CD variables).
- **Set `AIRUNNER_JWT_SECRET`** to a strong random value:
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- **Set `AIRUNNER_DEPLOYMENT_MODE=production`** to ensure the app refuses to
  start with a weak JWT secret.
- **Verify DNS records** (SPF, DKIM, DMARC) for your sending domain to
  maximize deliverability.  The transactional providers above have setup
  guides for this.

---

## Google OAuth — Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or select existing)
3. Navigate to **APIs & Services → Credentials**
4. Click **Create Credentials → OAuth client ID**
5. Application type: **Web application**
6. Name: "Airunner Auth"
7. **Authorized JavaScript origins:**
   - Development: `http://localhost:5173`
   - Production: `https://app.yourdomain.com`
8. **Authorized redirect URIs:**
   - Development: `http://localhost:5173/api/v1/auth/oauth/google/callback`
   - Production: `https://app.yourdomain.com/api/v1/auth/oauth/google/callback`
9. Copy the Client ID and Client Secret

**Configure `.env`:**
```env
AIRUNNER_GOOGLE_CLIENT_ID=xxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.apps.googleusercontent.com
AIRUNNER_GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxxxxxxxx
```

**Enable the Google People API** (used to fetch user info):
- Go to **APIs & Services → Library**
- Search for "Google People API" and enable it

### How the OAuth flow works

1. User clicks "Sign in with Google" → redirected to Google
2. Google asks for consent (email + profile scopes)
3. On approval, Google redirects to `/api/v1/auth/oauth/google/callback`
4. Server exchanges the auth code for user info
5. If user exists → logged in. If not → account created
6. Tokens sent to frontend via `/oauth/callback` redirect
7. Frontend stores tokens and redirects to app root

---

## Testing the Flow

### Registration flow
1. Navigate to `/register`
2. Fill in email, username, password, confirm password
3. Submit → see "Check your email" prompt
4. Check Mailpit/MailHog (dev) or your inbox (production)
5. Click the verification link → redirected to `/verify?token=xxx`
6. See "Email verified successfully"
7. Click "Sign In" → log in with email + password

### Google OAuth flow
1. Navigate to `/login` or `/register`
2. Click "Sign in with Google"
3. Complete Google consent flow
4. Redirected back to app → automatically signed in
