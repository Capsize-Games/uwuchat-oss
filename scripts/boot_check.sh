#!/usr/bin/env bash
# Boot check for the w3 worktree: verify the FastAPI app assembles with
# all routes registered after module decompositions.
#
# Usage: scripts/boot_check.sh [extra args]
set -u

cd "$(dirname "$0")/.."

docker run --rm \
  -v "$(pwd)/server:/app/server" \
  -v "$(pwd)/extensions:/app/extensions" \
  -v "$(pwd)/projects:/app/projects" \
  --entrypoint python3 \
  <registry>/<your-org>/<repo>:latest \
  -c "
import sys
sys.path.insert(0, '/app/server/src')
from fastapi import FastAPI
from airunner_services.api.server_routes import register_routes
app = FastAPI()
register_routes(app)
print('ROUTES:', len(app.routes))
" "$@"
