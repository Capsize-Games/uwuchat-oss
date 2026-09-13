# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# LAN web sidecar — static client build + nginx reverse proxy.
#
# Builds the client SPA for one AIRunner project and serves it with nginx,
# which also reverse-proxies /api (REST + WebSockets) to the `server`
# container on the same compose network.  This mirrors the private
# `uwuchat-caddy` edge behavior (extensions/docker/Dockerfile.caddy +
# Caddyfile) using nginx so the homeserver needs no Caddy edge container —
# its host Caddy reverse-proxies straight into this sidecar.
#
# Build context = AIRUNNER REPO ROOT (deploy/lan/uwuchat/docker-compose.yml
# sets `context: ../../..`).  The client build resolves project overlays
# (projects/<PROJECT>/client) and extension aliases (extensions/) relative
# to the repo root, so the whole tree must be in the build context.
#
# Parameterization:
#   --build-arg VITE_PROJECT=<project>   (required; e.g. uwuchat)
#   --build-arg VITE_DEPLOYMENT=cloud    (default; uwuchat + headlesscode
#                                         are cloud deployments — the LLM
#                                         inference host is injected as the
#                                         server-side ollama base URL, not a
#                                         browser edge deployment)
#
# Build (from repo root):
#   docker build -f deploy/lan/web/Dockerfile \
#       --build-arg VITE_PROJECT=uwuchat -t lan-web-uwuchat .
# ---------------------------------------------------------------------------

# ---- stage 1: build the SPA ----
FROM node:22-bookworm-slim AS build
ARG VITE_PROJECT
ARG VITE_DEPLOYMENT=cloud
WORKDIR /app
# Vite resolves @extensions to ../extensions, so both trees must be present.
COPY client ./client
COPY extensions ./extensions
COPY projects ./projects
WORKDIR /app/client
RUN npm ci && ln -s /app/client/node_modules /app/node_modules \
    && VITE_PROJECT="${VITE_PROJECT}" VITE_DEPLOYMENT="${VITE_DEPLOYMENT}" \
       npx vite build
# Output: /app/client/dist

# ---- stage 2: nginx serving the static build ----
FROM nginx:1.27-alpine
# nginx template: substitutes $SERVER_UPSTREAM at container start.
COPY deploy/lan/web/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/client/dist /usr/share/nginx/html
EXPOSE 80
