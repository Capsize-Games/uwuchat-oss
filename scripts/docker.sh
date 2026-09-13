#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Convenience wrapper around the dev Docker stack (open-core).
#
# Auto-detects an NVIDIA GPU and layers in docker-compose.gpu.yml when present,
# so `./scripts/docker.sh up` "just works" on both GPU and CPU machines.
# First run may prompt for missing credentials and saves them to
# projects/uwuchat/.env — no manual setup required.
#
# Usage:
#   ./scripts/docker.sh up                       # start the dev stack
#   ./scripts/docker.sh down
#
# Code mode (the headlesscode dashboard sidecar, code_mode_*.py) is
# DEFAULT-ON in dev: docker-compose.code-harness-local.yml is layered in
# whenever the `code-daemon` compose project's network exists (the coder
# daemon — see deploy/local/daemons/code-daemon/). When the daemon isn't
# running, the override is skipped with a warning instead of failing the
# stack. Set AIRUNNER_CODE_HARNESS=0 to disable code mode entirely.
#
# Also: build, logs [svc], migrate, shell, psql, test-eval, reset-data,
# recreate, auth, ps, restart, config — or any `docker compose` subcommand.
# ---------------------------------------------------------------------------
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

cmd="${1:-up}"
shift || true

usage() {
    cat >&2 <<'EOF'
Usage:
  ./scripts/docker.sh up                       # start the dev stack
  ./scripts/docker.sh up --with-code-harness    # + headlesscode sidecar
  ./scripts/docker.sh down

First run may prompt for missing credentials and saves them to
projects/uwuchat/.env — no manual setup.
EOF
}

# Code mode is default-on in dev (the headlesscode sidecar + daemon
# network join). Opt out with AIRUNNER_CODE_HARNESS=0. The old
# `--with-code-harness` flag is accepted and ignored (it's now the
# default) so existing muscle memory / scripts keep working.
CODE_HARNESS=1
if [[ "${AIRUNNER_CODE_HARNESS:-1}" == "0" ]]; then
    CODE_HARNESS=0
fi
args=()
for a in "$@"; do
    if [[ "${a}" == "--with-code-harness" ]]; then
        : # now the default — accept and ignore
    else
        args+=("${a}")
    fi
done
set -- "${args[@]+"${args[@]}"}"

AIRUNNER_ENV_FILE="projects/uwuchat/.env"
project="uwuchat"
# The service-level `env_file:` in docker-compose.yml is interpolated from
# this variable, and `--env-file` below selects it as the compose
# interpolation source too.
export AIRUNNER_ENV_FILE

# Mullvad rewrites the host's DNS resolver to an in-tunnel IP that changes
# on every reconnect/relay-switch. Docker's embedded DNS (127.0.0.11) can
# fail to forward to it correctly, causing "Temporary failure in name
# resolution" inside containers even though the host resolves fine. Read
# the host's current resolver fresh on every invocation and hand it to
# compose via env var substitution (see docker-compose.override.yml)
# instead of requiring a human to hand-edit a hardcoded IP each session.
detect_host_dns() {
    awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf 2>/dev/null
}

AIRUNNER_HOST_DNS="$(detect_host_dns)"
export AIRUNNER_HOST_DNS
if [[ -z "${AIRUNNER_HOST_DNS}" ]]; then
    echo "[docker.sh] WARNING: could not detect host DNS resolver from" \
         "/etc/resolv.conf — server container may fail to resolve" \
         "external hosts (pip installs, OpenRouter, etc.)." >&2
fi

COMPOSE=(docker compose --env-file "${AIRUNNER_ENV_FILE}" -f docker-compose.yml)
# Code mode is default-on: layer in the headlesscode override whenever the
# coder daemon's network exists (the daemon must be running — it's what
# code-mode sessions actually talk to). When the daemon isn't up, skip the
# override with a clear warning instead of failing the whole stack — chat
# still works (cloud/local chat daemon), only code mode is unavailable.
CODE_HARNESS_NETWORK="code-daemon_default"
if [[ "${CODE_HARNESS}" == "1" ]]; then
    if docker network inspect "${CODE_HARNESS_NETWORK}" >/dev/null 2>&1; then
        COMPOSE+=(-f docker-compose.code-harness-local.yml)
    else
        echo "[docker.sh] Code mode disabled: '${CODE_HARNESS_NETWORK}'" \
             "not found (the code-daemon coder daemon isn't running)." >&2
        echo "[docker.sh]   Start it with:" >&2
        echo "[docker.sh]     docker compose -f deploy/local/daemons/code-daemon/docker-compose.yml up -d" >&2
        echo "[docker.sh]   Or disable code mode: AIRUNNER_CODE_HARNESS=0 ./scripts/docker.sh up" >&2
    fi
fi

# An NVIDIA GPU is present and the driver is loaded? Detect via several
# signals, since `nvidia-smi` is not always on PATH even when the driver and
# device nodes exist (e.g. open-kernel-module installs).
host_has_nvidia_gpu() {
    { command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; } && return 0
    [[ -e /dev/nvidia0 ]] && return 0               # driver device node
    [[ -f /proc/driver/nvidia/version ]] && return 0 # kernel module loaded
    return 1
}

# Can Docker actually pass a GPU through? Requires nvidia-container-toolkit,
# which registers the `nvidia` runtime / CDI with the Docker daemon.
docker_gpu_ready() {
    docker info 2>/dev/null | grep -qiE '(^| )nvidia' && return 0
    command -v nvidia-ctk >/dev/null 2>&1 && return 0
    return 1
}

# Layer the GPU override in automatically, unless explicitly disabled with
# AIRUNNER_NO_GPU=1. If a GPU exists but Docker can't reach it, say so loudly
# and fall back to CPU instead of either silently degrading or hard-failing.
if [[ "${AIRUNNER_NO_GPU:-0}" == "1" ]]; then
    GPU_NOTE="(CPU only — AIRUNNER_NO_GPU=1)"
elif host_has_nvidia_gpu; then
    if docker_gpu_ready; then
        COMPOSE+=(-f docker-compose.gpu.yml)
        GPU_NOTE="(GPU enabled)"
    else
        GPU_NOTE="(CPU only)"
        cat >&2 <<'WARN'
[docker.sh] An NVIDIA GPU is present but Docker cannot access it — the
           nvidia-container-toolkit is not installed/configured, so the GPU
           override was skipped and the stack will run on CPU.

           To enable GPU (Debian/Ubuntu host):
             curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
               | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
             curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
               | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' \
               | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
             sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
             sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker

           Then re-run this command. See docker/README.md (GPU section).
WARN
    fi
else
    GPU_NOTE="(CPU only)"
fi

# Passing explicit -f flags above disables Compose's automatic pickup of
# docker-compose.override.yml, so layer it in explicitly when present. This
# file is gitignored (machine-local dev overrides, e.g. DNS fixes for a VPN
# on the host) and must come last so it wins over docker-compose.gpu.yml.
if [[ -f docker-compose.override.yml ]]; then
    COMPOSE+=(-f docker-compose.override.yml)
fi

# >>> BEGIN auto-provisioning functions
sanitize_value() {
    # Trim surrounding whitespace; values containing a newline are rejected
    # (returns empty) since they would corrupt the KEY=value line.
    local v="${1:-}"
    v="${v#"${v%%[![:space:]]*}"}"
    v="${v%"${v##*[![:space:]]}"}"
    if [[ "${v}" == *$'\n'* ]]; then
        echo ""
    else
        echo "${v}"
    fi
}

gen_jwt_secret() {
    # 32 random bytes hex-encoded; falls back to urandom+base64 when
    # openssl isn't installed on the host.
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 32
    else
        head -c 64 /dev/urandom | base64 | tr -d '\n=/+'
    fi
}

prompt_openrouter_key() {
    # Hidden-input prompt. Empty input re-prompts (max 3 attempts, then
    # error). A value that doesn't look like an OpenRouter key (sk-or-...)
    # warns once and re-prompts; whatever the user types next is accepted,
    # since some providers use a different format.
    local attempts=0 warned=0 key=""
    while (( attempts < 3 )); do
        attempts=$((attempts + 1))
        read -r -p "[docker.sh] Enter your OpenRouter API key (sk-or-...): " -s key
        # Newline to stderr only — hidden input doesn't echo Enter, and stdout
        # must stay clean for the key value (it is captured via $()).
        echo >&2
        key="$(sanitize_value "${key}")"
        if [[ -z "${key}" ]]; then
            echo "[docker.sh] Empty input — please enter the key (attempt ${attempts}/3)." >&2
            continue
        fi
        if [[ "${key}" != sk-or-* && ${warned} -eq 0 ]]; then
            warned=1
            echo "[docker.sh] WARNING: that doesn't look like an OpenRouter key" \
                 "(expected sk-or-...) — please double-check." >&2
            continue
        fi
        echo "${key}"
        return 0
    done
    echo "[docker.sh] ERROR: no OpenRouter API key entered after 3 attempts." >&2
    return 1
}

get_key_value() {
    # Reads KEY=value from the project env file; returns empty when absent.
    local key="${1}" val
    val="$(grep -E "^[[:space:]]*${key}=" "${AIRUNNER_ENV_FILE}" 2>/dev/null \
        | head -1 | cut -d= -f2- || true)"
    sanitize_value "${val}"
}

append_key() {
    # Appends KEY=value (preceded by a provenance comment) to the project
    # env file and echoes the key name so the caller can track what was
    # written. Callers only invoke this when the key is absent.
    local key="${1}" value="${2}" env_file="${AIRUNNER_ENV_FILE}"
    {
        printf '# added by scripts/docker.sh\n'
        printf '%s=%s\n' "${key}" "${value}"
    } >> "${env_file}"
    echo "${key}"
}

ensure_project_env() {
    # Zero-setup env provisioning. $1 = "full" (boot subcommands: prompts
    # allowed) or "file" (read-only subcommands: create the file only, no
    # credential prompting — genuinely required keys surface as compose's
    # own errors).
    local mode="${1:-file}" env_file="${AIRUNNER_ENV_FILE}"
    local added=() key="" joined=""

    # Compose's --env-file needs a real file to parse cleanly, so create
    # one (with a header) even for read-only subcommands.
    if [[ ! -f "${env_file}" ]]; then
        mkdir -p "$(dirname "${env_file}")"
        printf '# Created automatically by scripts/docker.sh — add or override keys below.\n' > "${env_file}"
    fi

    [[ "${mode}" == "full" ]] || return 0

    # OPENROUTER_API_KEY — interactive prompt with hidden input.
    if ! grep -Eq "^[[:space:]]*OPENROUTER_API_KEY=" "${env_file}"; then
        if ! key="$(prompt_openrouter_key)"; then
            exit 1
        fi
        added+=("$(append_key OPENROUTER_API_KEY "${key}")")
    fi

    # AIRUNNER_JWT_SECRET — auto-generated, never prompted.
    if ! grep -Eq "^[[:space:]]*AIRUNNER_JWT_SECRET=" "${env_file}"; then
        added+=("$(append_key AIRUNNER_JWT_SECRET "$(gen_jwt_secret)")")
    fi

    # The headlesscode sidecar (code mode, default-on) mirrors the
    # OpenRouter key under its own var name (same value, no second
    # prompt) — it's required at the CLI's startup validation gate even
    # for a local-backend session.
    if [[ "${CODE_HARNESS}" == "1" ]] \
        && ! grep -Eq "^[[:space:]]*HEADLESSCODE_OPENROUTER_API_KEY=" "${env_file}"; then
        key="$(get_key_value OPENROUTER_API_KEY)"
        if [[ -n "${key}" ]]; then
            added+=("$(append_key HEADLESSCODE_OPENROUTER_API_KEY "${key}")")
        fi
    fi

    if [[ ${#added[@]} -gt 0 ]]; then
        printf -v joined '%s, ' "${added[@]}"
        joined="${joined%, }"
        echo "[docker.sh] ${project}: wrote ${joined} to ${env_file}"
    fi
}
# <<< END auto-provisioning functions

# Zero-setup env provisioning: full credential ensure for subcommands that
# boot/need the stack; file-existence only for read-only subcommands.
case "${cmd}" in
    up|migrate|recreate|reset-data|test-eval|test-eval-rpc|shell|psql|auth)
        ensure_project_env full
        ;;
    *)
        ensure_project_env file
        ;;
esac

case "${cmd}" in
    up)
        WANT_CLIENT=()
        for a in "$@"; do [[ "${a}" == "--client" ]] && WANT_CLIENT=(--profile client); done
        echo "Starting ${project} dev stack ${GPU_NOTE}..."
        exec "${COMPOSE[@]}" "${WANT_CLIENT[@]}" up -d
        ;;
    down)    exec "${COMPOSE[@]}" --profile client down "$@" ;;
    build)   exec "${COMPOSE[@]}" build "$@" ;;
    logs)    exec "${COMPOSE[@]}" logs -f "$@" ;;
    migrate) exec "${COMPOSE[@]}" run --rm server \
                python -c "import sys; sys.path.insert(0,'/app/server/src'); from airunner_services.database.setup_database import setup_database; setup_database()" ;;
    shell)   exec "${COMPOSE[@]}" exec server bash ;;
    psql)    exec "${COMPOSE[@]}" exec db psql -U "${POSTGRES_USER:-airunner}" -d "${POSTGRES_DB:-airunner}" ;;
    test-eval)
        # Run RAG eval tests inside the running server container.
        # The server must already be up:  ./scripts/docker.sh up
        # Optional args are forwarded to pytest, e.g.:
        #   ./scripts/docker.sh test-eval -v -k test_llm_retrieves
        echo "Running RAG eval tests in the server container..."
        exec "${COMPOSE[@]}" exec -T server \
            python -m pytest server/tests/eval/ \
            -p no:cacheprovider \
            --tb=short --color=yes -ra \
            --timeout=600 \
            "$@"
        ;;
    test-eval-rpc)
        # Run the RPC-based support smoke-test (fast, no LLM model required).
        echo "Running eval support smoke test..."
        exec "${COMPOSE[@]}" exec -T server \
            python -c "
import sys
sys.path.insert(0, '/app/server/src')
from airunner_services.api.routes.health import build_health_payload
print('RPC support module import OK')
print('Health payload:', build_health_payload('ok'))
"
        ;;
    reset-data)
        echo "WARNING: This will permanently delete all database data." >&2
        read -r -p "Type 'yes' to confirm: " confirm
        [[ "${confirm}" == "yes" ]] || { echo "Aborted." >&2; exit 1; }
        echo "Stopping stack..."
        "${COMPOSE[@]}" --profile client down
        # The named volume is prefixed with the compose project name at runtime
        # (e.g. airunner_airunner_pgdata), so a bare `docker volume rm
        # airunner_pgdata` silently misses it. Resolve the real name instead.
        echo "Removing postgres volume..."
        pg_vol="$(docker volume ls --format '{{.Name}}' | grep -E '(^|_)airunner_pgdata$' | head -1)"
        if [[ -n "${pg_vol}" ]]; then
            docker volume rm "${pg_vol}"
        else
            echo "[docker.sh] No airunner_pgdata volume found (already clean?)." >&2
        fi
        # Bring up ONLY the database first. The app server runs setup_database()
        # on boot, so starting it now would race the explicit migration below
        # and collide creating alembic_version. Migrate in a one-off container
        # while the server is down, then start the full stack (its boot-time
        # setup_database() then sees the schema at head and skips).
        echo "Starting database..."
        "${COMPOSE[@]}" up -d db
        echo "Waiting for database..."
        for i in $(seq 1 30); do
            "${COMPOSE[@]}" exec -T db pg_isready -U "${POSTGRES_USER:-airunner}" -q && break
            sleep 2
        done
        echo "Running migrations..."
        "${COMPOSE[@]}" run --rm --no-deps server \
            python -c "import sys; sys.path.insert(0,'/app/server/src'); from airunner_services.database.setup_database import setup_database; setup_database()"
        echo "Starting stack..."
        "${COMPOSE[@]}" up -d
        echo "Done — database has been reset."
        ;;
    # Recreate one or more services, re-reading the project env file (unlike `restart`).
    # Usage: ./scripts/docker.sh recreate [service ...]
    # Example: ./scripts/docker.sh recreate server
    recreate)
        services=("$@")
        if [[ ${#services[@]} -eq 0 ]]; then
            exec "${COMPOSE[@]}" up -d --force-recreate
        else
            exec "${COMPOSE[@]}" up -d --force-recreate "${services[@]}"
        fi ;;
    auth)    # Account management for the auth extension, e.g.:
             #   ./scripts/docker.sh auth create-user --email a@b.c \
             #       --username admin --password 'secret123' --superuser
             #   ./scripts/docker.sh auth list
             exec "${COMPOSE[@]}" exec server \
                python -m extensions.auth.server.manage "$@" ;;
    *)       exec "${COMPOSE[@]}" "${cmd}" "$@" ;;
esac
