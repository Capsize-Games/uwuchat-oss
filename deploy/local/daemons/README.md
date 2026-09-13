# Local-dev GPU inference daemons (UwUchat, LOCAL DEV ONLY)

The `<private-desktop-repo>` daemons (a **separate repo**,
`~/Projects/<private-desktop-repo>` — configure and call, never edit its Python
source from this repo) run in `--ollama-mode` (an Ollama-API-compatible
HTTP server), each holding one GGUF model on the local RTX 5080
(16GB VRAM total). Only ONE should be loaded at a time — they share the
same GPU and do not fit together (see the GPU model-switching design doc
for the VRAM-contention history).

**Default (dev override): chat and code share the Qwen3-14B code daemon.**
`docker-compose.code-harness-local.yml` sets both chat
(`UWUCHAT_CHAT_DAEMON_URL`/`UWUCHAT_CHAT_DAEMON_CONTAINER`) and code
(`HEADLESSCODE_OLLAMA_URL`) at the same container, so the GPU switch is a
no-op. When chat and code use SEPARATE daemons, only one may be loaded at
a time and the switch arbitrates them.

A THIRD daemon (review-daemon) runs on a completely separate machine
(the staging server `<staging-hostname>`, RTX 2080 SUPER) — no VRAM contention with the
two below, see its own section further down.

| Daemon | Compose project | Container | Port | Model | Used by |
|---|---|---|---|---|---|
| Chat | `lan-daemon` | `lan-daemon-daemon-1` | `0.0.0.0:11434` | `Qwen3.5-9B-Q8_0.gguf` | UwUchat DIALOGUE when chat uses a separate daemon from code |
| Code | `code-daemon` | `code-daemon-daemon-1` | `0.0.0.0:11435` | `Qwen3-14B-Q4_K_M.gguf` | headlesscode `code`-mode sessions AND (default) UwUchat DIALOGUE chat |
| Review (on `<staging-hostname>`, not this box) | `review-daemon` | — | `<staging-hostname>:11500` | `DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf` | Not yet wired to any mode — infra only, see issue #147 |

## How the GPU inference mode is toggled

Chat and code models are independently configurable. When they use
**different** daemon containers, toggling code mode loads only the daemon
matching the new mode:

| Code mode | DIALOGUE (main UwUChat chat) | GPU state |
|---|---|---|
| **ON** | the configured chat daemon (default: shared Qwen3-14B) | code daemon loaded; chat daemon stopped |
| **OFF** | the configured chat daemon (default: shared Qwen3-14B) | chat daemon loaded; code daemon stopped |

When chat and code share the SAME daemon container (the default), the
switch **no-ops** — `gpu_inference_mode.apply_code_mode` returns True
without touching any container (`_same_daemon()` guard), because
stopping the single daemon would drop the model both modes depend on.

The switch is fired by `code_mode_service.set_code_mode()` via a Celery
task (`projects/uwuchat/server/tasks/gpu_inference_tasks.py`), which
calls `gpu_inference_mode.apply_code_mode(enabled)`. See those modules
for the current mechanism (native HTTP `/unload` + `docker start/stop`).

## Manual start/stop (debugging)

```bash
# Chat daemon (Qwen3.5-9B) — only when chat uses a separate daemon from code
docker compose -f deploy/local/daemons/chat-daemon/docker-compose.yml up -d
docker compose -f deploy/local/daemons/chat-daemon/docker-compose.yml down

# Code daemon (Qwen3-14B coder) — code mode + (default) DIALOGUE chat
docker compose -f deploy/local/daemons/code-daemon/docker-compose.yml up -d
docker compose -f deploy/local/daemons/code-daemon/docker-compose.yml down
```

Verify what's loaded:

```bash
curl http://127.0.0.1:11434/api/tags   # chat daemon (if running)
curl http://127.0.0.1:11435/api/tags   # code daemon
nvidia-smi                              # confirm VRAM actually moved
```

Both compose projects use `name:` so the pre-existing containers
(`lan-daemon-daemon-1`, `code-daemon-daemon-1`) are adopted rather than
duplicated.

## Why these files live here

Previously these compose files lived in an ephemeral `/tmp/claude-*/...`
scratchpad (code daemon) and a disposable worktree
(`.worktrees/w14/deploy/lan/daemon/`, chat daemon) — fragile locations
that could vanish with no recovery path. They're now git-tracked here for
durability and stable paths for the GPU-mode-switching feature.

> **Do not touch `deploy/lan/`** — that's the `<staging-hostname>` LAN staging config,
> out of scope for local-dev GPU work.

## Review daemon (on `<staging-hostname>`, not this box)

`review-daemon/docker-compose.yml` targets the RTX 2080 SUPER on the
staging server `<staging-hostname>` (<staging-ip>), not this dev box's 5080 — see the
compose file's own header comment for full context and the exact
scp+ssh deploy steps (it can't just run `docker compose up` locally the
way the chat/code daemons do, since the target GPU is on a different
machine). Built as infrastructure for GitHub issue
`<your-org>/<repo>#147` — standing up a dedicated local model
for lighter-weight modes (ask, debug, qa-agent, audit, reviewer) so
they don't contend with the coder model's VRAM or need a cloud
round-trip. **Not yet wired to any UwUChat mode** — that's separate,
larger follow-up work, intentionally out of scope for the initial
daemon standup.

**GPU-accelerated, confirmed** (~78-85 tok/s) — root cause of the
earlier CPU-only fallback found and fixed: <staging-hostname>'s Docker only has the
legacy `nvidia` runtime registered (no OCI hook for the `--gpus`
flag), so `--gpus all` / Compose's `gpus:` / `deploy.reservations`
all silently produced a container with no real device access.
`runtime: nvidia` (this file's current config) is what actually works
on this host, verified via both `docker run --runtime=nvidia` and
`docker compose up` with this file. See the compose file's own header
comment for the full investigation.
