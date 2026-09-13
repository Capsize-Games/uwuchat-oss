# LAN Deployment — uwuchat on the home server

This directory holds the versioned Docker stack that runs the **uwuchat**
website on the home server (`<homeserver-hostname>`, <homeserver-ip>) behind its Caddy reverse
proxy. Chat inference is normally served by the **shared local inference
daemon** on the workstation (an ollama-compatible endpoint the homeserver
reaches over the LAN). The stack also bundles the **headlesscode dashboard
sidecar**, which backs `launch_headlesscode_session` / code mode — a
per-conversation admin toggle that swaps the bot into a coding-assistant
role and dispatches coding tasks to a headless agent running against a
registered project. Code mode sessions run on a *separate* workstation
daemon from website chat (a different model, a different port — see
"Flipping the inference host" below).

```
                LAN
   workstation (ollama daemon :11434, coder daemon :11435)
        ▲                        ┌──────────── homeserver (<homeserver-hostname>) ───────────┐
        │  AIRUNNER_OLLAMA_BASE_URL                                        │
        │  HEADLESSCODE_OLLAMA_URL                                         │
        │                        │   host Caddy (:80/:443)                 │
        │                        └───────┬─────────────────────────────────┘
        │                     homeserver_hs_net (external compose network) │
        │                                │                                  │
        │                    ┌───────────▼───────────┐                      │
        │                    │   web (nginx sidecar) │  serves SPA, proxies │
        │                    └───────────┬───────────┘  /api + WS to server │
        │                                │                                  │
        │                    ┌───────────▼───────────┐                      │
        └───────────────────▶│ server (+ celery*,   │                       │
                             │  redis, db, headlesscode — internal)│         │
                             └───────────────────────┘                      │
```

The stack lives here:

- [`uwuchat/`](uwuchat/) — `docker-compose.yml` + `.env.example`
- [`web/`](web/) — nginx sidecar build context (Dockerfile + config)

At runtime the stack is **image-based** (no source bind-mounts into the
running containers). The `web` sidecar is built on the homeserver, and its
Dockerfile needs the repo tree (`client/`, `extensions/`, `projects/`) in the
build context — so a repo checkout (or a copy of those trees plus
`deploy/lan/`) must be present on the homeserver. The cleanest way is a
`git clone` (step 1 below).

---

## Prerequisites (homeserver + workstation)

1. **GHCR auth on the homeserver.** The server/celery images come from the
   private registry `<registry>/<your-org>`. Create a GitHub
   Personal Access Token with **`read:packages`** scope (and `repo` if the
   package is private to the org) and log in on the homeserver:

   ```bash
   echo "$GHCR_PAT" | docker login ghcr.io -u <github-username> --password-stdin
   ```

   Add this to the homeserver's Docker init so it survives reboots (e.g. a
   `~/.docker/config.json` owned by the Docker service user, or a systemd
   drop-in that runs the login before `docker start`).

2. **Workstation stable LAN IP.** The homeserver reaches the inference daemon
   at a fixed address, e.g. `<workstation-ip>`. Assign a static lease/DHCP
   reservation on your router so it never changes.

3. **Qwen3-14B on the workstation.** The shared daemon must serve the
   Qwen3-14B coder GGUF (default `AIRUNNER_LLM_MODEL=qwen3-14b`), and the
   code daemon must be reachable at the configured
   `AIRUNNER_OLLAMA_BASE_URL` / `HEADLESSCODE_OLLAMA_URL`. Daemon + router
   bring-up is an **ops task** — see the ops runbook. Chat (DIALOGUE) and
   code mode share this ONE daemon (same host:port), so a single model
   load serves both and there is no second-VRAM contention.

4. **Caddy on the homeserver** with the `homeserver_hs_net` compose network.
   The homeserver compose stack creates that network and attaches its Caddy
   container to it; the LAN stack joins it and Caddy reverse-proxies the
   site's domain to the matching `web` container.

5. **Docker + compose plugin** on the homeserver (no systemd — Docker starts
   at boot; every service uses `restart: unless-stopped`).

6. **`headlesscode:0.1.0` image on the homeserver**, built from a
   headlesscode checkout containing the `POST /api/session/:id/message`
   route (master since 2026-08-04) and the `POST /api/projects/
   ensure-worktree` route (master since 2026-08-20) — see
   `extensions/docker/docker-compose.headlesscode.yml`. This backs the
   `headlesscode` sidecar service in the compose file below.

---

## Server/celery image — use `airunner:lan` (IMPORTANT)

The base compose references `<registry>/<your-org>/airunner:latest`
(open-core, built from `docker/Dockerfile`). **Do not deploy the LAN stack
with that image as-is** — it does not ship the private `extensions/` package,
so the initial-schema migration crash-loops with
`ModuleNotFoundError: extensions.auth.server.models`. The production image
(`<registry>/<your-org>/uwuchat-server`, from the private
`extensions/docker/Dockerfile.prod`) does ship extensions but **lacks celery**,
so its celery workers crash-loop with `exec: celery: not found` (exit 127).

The correct image is **`airunner:lan`** = `airunner:latest` + extensions baked
in + installed (it has both celery and extensions, and the W2/W3 env
plumbing). Build and push it once from the repo root:

```bash
docker build -f deploy/lan/Dockerfile.lan \
  -t <registry>/<your-org>/airunner:lan .
docker push <registry>/<your-org>/airunner:lan
```

(Requires GHCR read auth for the `airunner:latest` base image and write auth
for the push. The Dockerfile intentionally COPYs `extensions/` — the open-core
boundary is enforced by the fact that `deploy/lan/Dockerfile.lan` is the only
open-repo Dockerfile that does so, mirroring the private prod Dockerfile.)

**<homeserver-hostname>-local override (not committed):** the stack needs a
`docker-compose.override.yml` that (a) points `server` + the three `celery*`
services at `airunner:lan`, and (b) sets `cpus: 0` on the celery services —
the <homeserver-hostname> kernel (Debian trixie) has no CPU CFS quota support, so the base
file's `cpus:` limits fail container creation ("NanoCPUs can not be set").

**Auth:** the `server` service sets `AIRUNNER_EXTENSIONS=extensions.auth.config`
by default — required so the LAN site has a login. On a fresh database there
are no accounts, so after first `up` create one:

```bash
docker compose exec server python -m extensions.auth.server.manage create-user \
  --email you@example.com --username <name> --password '<strong passphrase>' \
  --superuser
```

---

## Deploy

### 1. Get the repo onto the homeserver

The `web` sidecar builds from the **repo root** (`context: ../../..` — the
Dockerfile COPYs `client/`, `extensions/`, `projects/`), so those trees must
exist on the homeserver. The recommended layout is a plain `git clone`:

```bash
ssh <homeserver-hostname>
cd /opt
git clone <airunner-repo-url> lan
cd /opt/lan
```

Now `deploy/lan/uwuchat/docker-compose.yml` sits at
`/opt/lan/deploy/lan/uwuchat/`, and the web build's `context: ../../..`
resolves to `/opt/lan` (the repo root) — which contains `client/`,
`extensions/`, and `projects/`. The homeserver layout:

```
/opt/
└── lan/                         # git clone of the airunner repo
    ├── client/                  # required by the web sidecar build
    ├── extensions/              # required by the web sidecar build
    ├── projects/                # required by the web sidecar build
    ├── deploy/lan/
    │   ├── README.md
    │   ├── uwuchat/
    │   │   ├── docker-compose.yml
    │   │   ├── .env               # created in step 2
    │   │   └── headlesscode-store/ # created on first up (dashboard data)
    │   └── web/                 # Dockerfile + nginx template
    │       ├── Dockerfile
    │       └── nginx/default.conf.template
    └── … (server/, scripts/, …)
```

Copying **only** `deploy/lan/` (or only `deploy/lan/web`) will **NOT work** —
the web build context would lack `client/`, `extensions/`, and `projects/`,
and the multi-stage Dockerfile would fail its COPY steps.

### 2. Configure `.env`

On the homeserver:

```bash
cd /opt/lan/deploy/lan/uwuchat
cp .env.example .env
$EDITOR .env
```

Fill in at minimum:

- `POSTGRES_PASSWORD` — strong random value
- `AIRUNNER_OLLAMA_BASE_URL` — `http://<workstation-ip>:11434`
- `AIRUNNER_JWT_SECRET` — `openssl rand -hex 32` (or equivalent)
- `OPENROUTER_API_KEY` — used by ai_pipeline.py's DIALOGUE default AND by
  the headlesscode sidecar (required at its CLI startup even for a
  local-backend session)
- `HEADLESSCODE_DASHBOARD_TOKEN` — strong random value (dashboard
  control-plane auth)
- `HEADLESSCODE_OLLAMA_URL` — `http://<workstation-ip>:11435` (the shared
  workstation's coder daemon — see "Flipping the inference host" below; a
  different port from `AIRUNNER_OLLAMA_BASE_URL`, a different daemon)
- `AIRUNNER_INSECURE_NO_AUTH` — leave unset (`production` mode requires an
  API key or the auth extension); set to `1` **only** for a private LAN
  deployment without auth, and never when the site is reachable beyond your
  LAN

`.env` is gitignored — never commit it.

### 3. Start the stack

```bash
cd /opt/lan/deploy/lan/uwuchat && docker compose up -d --build
docker compose ps
```

Migrations run automatically on server boot (entrypoint). The first boot
creates the tenant schema and the default superuser/admin accounts per the
project's normal bootstrap.

### 4. Reload Caddy

Once the `web` container is up, add (or update) the reverse-proxy site block
on the homeserver Caddy:

```
uwuchat.example.com {
    reverse_proxy web:80
}
```

`web` is reachable from Caddy because both are attached to the external
`homeserver_hs_net` network (the homeserver compose stack creates that
network and attaches its Caddy container to it; the wildcard
`*.example.com` Let's Encrypt cert already covers the subdomain).
Reload:

```bash
docker exec <caddy-container> caddy reload --config /etc/caddy/Caddyfile
```

### 5. Verify

```bash
curl -fsS https://uwuchat.example.com/api/v1/health      # via Caddy → web → server
curl -fsS https://uwuchat.example.com/                    # SPA served by nginx
docker compose -f /opt/lan/deploy/lan/uwuchat/docker-compose.yml logs -f server web headlesscode
```

---

## Flipping the inference host

**Website chat (DIALOGUE)**: a single env knob on the `server` (and
`celery*`) services, all sourced from `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `AIRUNNER_LLM_PROVIDER` | `ollama` | provider backend for the shared daemon |
| `AIRUNNER_LLM_MODEL` | `qwen3-14b` | model name the daemon/router serves |
| `AIRUNNER_OLLAMA_BASE_URL` | `http://<workstation-ip>:11435` | daemon endpoint (the SAME coder daemon code mode uses) |

To point website chat at a different inference host (e.g. a backup daemon, or
the daemon on a new workstation):

1. Edit `AIRUNNER_OLLAMA_BASE_URL` in `deploy/lan/uwuchat/.env`.
2. Recreate the services so the new value takes effect:

   ```bash
   cd /opt/lan/deploy/lan/uwuchat && docker compose up -d --force-recreate server celery celery-sync
   ```

3. Verify with a chat message; the server logs the provider used.

To flip website chat back to cloud (OpenRouter) entirely, set
`AIRUNNER_LLM_PROVIDER=openrouter`, add `OPENROUTER_API_KEY`, and force-recreate
the same services.

**Code mode**: `launch_headlesscode_session` sessions are always local — the
only knob is `HEADLESSCODE_OLLAMA_URL` on the `headlesscode` service
(`deploy/lan/uwuchat/.env`), which points them at the shared workstation's
coder daemon. Editing it + `docker compose up -d --force-recreate headlesscode`
is the equivalent flip. By default `HEADLESSCODE_OLLAMA_URL` and
`AIRUNNER_OLLAMA_BASE_URL` point at the SAME daemon (Qwen3-14B), so website
chat and code mode share one model load. Point them at different daemons to
use separate chat and code models (and set the GPU switch's
`UWUCHAT_CHAT_DAEMON_CONTAINER`/`UWUCHAT_CODE_DAEMON_CONTAINER` on the dev
stack accordingly if you want the switch to arbitrate them).

---

## Teardown

```bash
cd /opt/lan/deploy/lan/uwuchat && docker compose down          # keeps named volumes
```

`down -v` additionally removes the `pgdata`/`redis_data`/`server_data`
volumes (irrecoverable data loss — backup first if you care).

Remove the Caddy site block and reload Caddy to stop routing to the stack.

---

## Debugging ports

By default **no** host ports are published for `db`/`redis`; the `server`
port is published only for host-side debugging (`AIRUNNER_HTTP_PORT`,
default `8080`). Caddy routes into `web`, not `server`. The `headlesscode`
sidecar publishes nothing — it shares `server`'s netns and binds
`127.0.0.1:4390` only, by design.

To publish Postgres for debugging, uncomment in the compose file:

```yaml
ports: ["${POSTGRES_PORT:-5434}:5432"]
```

Never expose these beyond the LAN.
