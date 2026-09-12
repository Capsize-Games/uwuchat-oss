# deploy/lan/web — shared web sidecar for the LAN stacks
#
# Builds the client SPA for one AIRunner project and serves it via nginx,
# reverse-proxying /api (REST + WebSockets) to the `server` container.
# Both LAN stacks reference this context (`web` service, `build: ../web`);
# the homeserver's Caddy reverse-proxies into this sidecar.
#
# Parameterization (build args):
#   VITE_PROJECT=<project>   required — uwuchat | headlesscode
#   VITE_DEPLOYMENT=cloud    default — the LAN stacks are cloud deployments
#                            (the shared inference daemon is a server-side
#                            ollama base URL, not a browser edge device)
#
# Runtime env (from the stack's .env via compose):
#   SERVER_UPSTREAM         default server:8080 — nginx proxies /api here
#
# Build from the repo root:
#   docker build -f deploy/lan/web/Dockerfile \
#       --build-arg VITE_PROJECT=uwuchat -t lan-web-uwuchat .
#
# The image is intentionally self-contained (no source bind-mounts) so it
# runs on the homeserver without the repo checkout.  The compose files build
# it with the repo as context; the homeserver build needs only the repo files
# (scp'd or a git clone on the homeserver).
