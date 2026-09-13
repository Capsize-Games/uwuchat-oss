#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Container entrypoint shared by the dev (open-core) and prod (extensions)
# images. Waits for PostgreSQL to accept connections, applies migrations, then
# execs the given command (the API server by default).
# ---------------------------------------------------------------------------
set -euo pipefail

log() { echo "[entrypoint] $*"; }

# ---------------------------------------------------------------------------
# 1. Wait for the database.
#
# Uses psycopg (a core dependency) against the same DATABASE_URL the app
# resolves, so we honour AIRUNNER_DATABASE_URL / AIRUNNER_POSTGRES_* exactly.
# ---------------------------------------------------------------------------
if [[ "${AIRUNNER_SKIP_DB_WAIT:-0}" != "1" ]]; then
    log "Waiting for PostgreSQL..."
    python - <<'PY'
import os
import sys
import time

# Resolve the same URL the application will use.
sys.path.insert(0, "/app/server/src")
try:
    from airunner_services.conf import settings
    url = settings.DATABASE_URL
except Exception:
    url = (
        os.environ.get("AIRUNNER_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    )

import psycopg

deadline = time.time() + int(os.environ.get("AIRUNNER_DB_WAIT_TIMEOUT", "60"))
last_err = None
while time.time() < deadline:
    try:
        # psycopg v3's connect() does not understand the SQLAlchemy-specific
        # "+driver" suffix (e.g. postgresql+psycopg://).  Strip it here.
        _sanitized = url.replace("+psycopg", "", 1) if "+psycopg" in url else url
        with psycopg.connect(_sanitized, connect_timeout=3):
            print("[entrypoint] PostgreSQL is ready.")
            break
    except Exception as exc:
        last_err = exc
        time.sleep(1.5)
else:
    print(f"[entrypoint] Database not reachable: {last_err}", file=sys.stderr)
    sys.exit(1)
PY
fi

# ---------------------------------------------------------------------------
# 1b. Install dependencies for bind-mounted extensions (dev only).
#
# The dev image (open-core) installs only the core `server` package; the
# private extensions/ tree is bind-mounted at runtime and is NOT in the build
# context, so its third-party deps (slowapi, pyjwt, …) are not present. Without
# them, the extension loader silently swallows the ModuleNotFoundError and the
# extension's routes never register (e.g. /api/v1/auth/* → 404).
#
# In the prod image these deps are already baked in at build time
# (Dockerfile.prod installs requirements-prod.txt into site-packages
# directly), and prod's PYTHONPATH never includes /opt/ext-deps, so
# this step is both redundant and unused there. Dockerfile.prod sets
# AIRUNNER_SKIP_EXT_DEPS=1 to skip it unconditionally.
#
# In dev, they are installed into a named volume (/opt/ext-deps) that
# survives container recreation, so a Mullvad reconnect or transient DNS
# blip during `docker compose up` no longer crash-loops the server —
# once the install succeeds once, every future start skips it unless
# the pinned requirements file actually changes.
# ---------------------------------------------------------------------------
EXT_REQS="/app/extensions/docker/requirements-prod.txt"
EXT_DEPS_DIR="/opt/ext-deps"
EXT_DEPS_MARKER="${EXT_DEPS_DIR}/.installed-hash"
if [[ "${AIRUNNER_SKIP_EXT_DEPS:-0}" != "1" \
      && -n "${AIRUNNER_EXTENSIONS:-}" \
      && -f "${EXT_REQS}" ]]; then
    mkdir -p "${EXT_DEPS_DIR}"
    NEW_HASH="$(sha256sum "${EXT_REQS}" | awk '{print $1}')"
    OLD_HASH="$(cat "${EXT_DEPS_MARKER}" 2>/dev/null || true)"
    if [[ "${NEW_HASH}" != "${OLD_HASH}" ]]; then
        log "Installing bind-mounted extension dependencies..."
        pip install --no-input --target "${EXT_DEPS_DIR}" -r "${EXT_REQS}"
        echo "${NEW_HASH}" > "${EXT_DEPS_MARKER}"
    else
        log "Bind-mounted extension dependencies already installed" \
            "(requirements unchanged) — skipping."
    fi
fi

# ---------------------------------------------------------------------------
# 2. Apply migrations (core + extensions).
#
# setup_database() also runs on server boot, but doing it here makes failures
# explicit and lets `migrate` be run as a one-off task in CI / deploys.
# ---------------------------------------------------------------------------
if [[ "${AIRUNNER_SKIP_MIGRATE:-0}" != "1" ]]; then
    log "Applying database migrations..."
    python - <<'PY'
import sys
sys.path.insert(0, "/app/server/src")
from airunner_services.database.setup_database import setup_database
setup_database()
print("[entrypoint] Migrations applied.")
PY
fi

# ---------------------------------------------------------------------------
# 3. Dev reload (optional).  When AIRUNNER_DEV_RELOAD=1, wrap the server
#    command with the watchdog-based reloader so Python source file changes
#    trigger an automatic restart.
# ---------------------------------------------------------------------------
if [[ "${AIRUNNER_DEV_RELOAD:-0}" == "1" ]]; then
    log "Dev reload ENABLED — server will restart on source changes."
    log "Watch paths: ${AIRUNNER_DEV_RELOAD_PATHS:-/app/server/src}"
    log "Debounce interval: ${AIRUNNER_DEV_RELOAD_DEBOUNCE:-1.0}s"
    exec python -m airunner_services.dev_reload "$@"
fi

# ---------------------------------------------------------------------------
# 4. Ensure `/app` (project root) is on Python's import path so project
#    modules in `projects/` can be resolved via `import projects.uwuchat.*`.
# ---------------------------------------------------------------------------
export PYTHONPATH="/app${PYTHONPATH:+:${PYTHONPATH}}"

# ---------------------------------------------------------------------------
# 5. DNS health check (dev environments behind a VPN).
#
# Mullvad rewrites the host's DNS resolver IP on every reconnect or relay
# switch.  Docker's per-container ``dns:`` list is baked in at container
# creation and does not update mid-life, so a container that outlives a
# relay switch silently sits on a stale resolver.
#
# This check probes resolution of an external host that the app depends
# on (Open-Meteo) and logs a loud, actionable warning when it fails so
# the operator knows to recreate the container with ``scripts/docker.sh``.
# The check is non-fatal — a transient DNS blip must not prevent the
# entire server (auth, chat, etc.) from starting.
# ---------------------------------------------------------------------------
log "Checking outbound DNS resolution..."
python -c "
import socket
try:
    socket.getaddrinfo('api.open-meteo.com', 443)
    print('[entrypoint] DNS resolution OK')
except Exception as exc:
    print('[entrypoint] DNS RESOLUTION FAILED for api.open-meteo.com')
    print('[entrypoint] This usually means the host DNS resolver changed')
    print('[entrypoint] (e.g. Mullvad relay switch).  Re-run:')
    print('[entrypoint]   ./scripts/docker.sh recreate server')
    print('[entrypoint] Full error: {}'.format(exc))
" || log "DNS health check produced warnings (see above)."

# ---------------------------------------------------------------------------
# 6. Hand off to the requested command.
# ---------------------------------------------------------------------------
log "Starting: $*"
exec "$@"
