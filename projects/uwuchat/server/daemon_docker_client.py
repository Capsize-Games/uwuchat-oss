"""Thin Docker Engine API client for the local GGUF daemons.

Speaks the Docker Engine HTTP API over the mounted unix socket
(``/var/run/docker.sock``) using httpx's unix-socket transport — no
docker CLI or docker-py required inside the container (neither is
installed). Used by ``gpu_inference_mode`` to docker stop/start the
chat/code daemon containers when code mode toggles.

See plans/uwuchat-code-mode-gpu-model-switching.md Decision A: the
daemons' native HTTP /unload APIs are confirmed no-ops (return success
while VRAM stays flat), so container stop/start is the only reliable
mechanism. The docker socket is mounted read-only into the ``celery``
container via docker-compose.code-harness-local.yml.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# Docker Engine API unix socket (mounted into the celery container).
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")

_ACTION_TIMEOUT_SECONDS = 60.0


def _docker_client() -> httpx.Client:
    """Return an httpx client speaking the Docker Engine API over the
    mounted unix socket."""
    return httpx.Client(
        base_url="http://docker",
        transport=httpx.HTTPTransport(uds=DOCKER_SOCKET),
        timeout=_ACTION_TIMEOUT_SECONDS,
    )


def container_state(container: str) -> str | None:
    """Return the container's running state ("running"/"exited"), or
    None when the container doesn't exist or the lookup fails."""
    try:
        with _docker_client() as client:
            resp = client.get(f"/containers/{container}/json")
        if resp.status_code != 200:
            return None
        state = resp.json().get("State", {})
        return state.get("Status")
    except Exception as exc:
        logger.warning("Docker API state lookup failed: %s", exc)
        return None


def start_container(container: str) -> bool:
    """Start *container* via the Docker Engine API.

    Returns True when the container is running afterward (started now or
    already running). Never raises — logs and returns False on failure.
    """
    try:
        current = container_state(container)
        if current == "running":
            logger.info("Daemon %s already running", container)
            return True
        with _docker_client() as client:
            resp = client.post(f"/containers/{container}/start")
        if resp.status_code not in (204, 304):
            logger.error(
                "Failed to start daemon %s: HTTP %s %s",
                container, resp.status_code, resp.text[:200],
            )
            return False
        logger.info("Started daemon %s", container)
        return True
    except Exception as exc:
        logger.error("Failed to start daemon %s: %s", container, exc)
        return False


def stop_container(container: str) -> bool:
    """Stop *container* via the Docker Engine API.

    Returns True when the container is stopped afterward (stopped now or
    already stopped). Never raises — logs and returns False on failure.
    """
    try:
        current = container_state(container)
        if current in ("exited", "created", "dead"):
            logger.info("Daemon %s already stopped (%s)", container, current)
            return True
        with _docker_client() as client:
            resp = client.post(f"/containers/{container}/stop")
        if resp.status_code not in (204, 304):
            logger.error(
                "Failed to stop daemon %s: HTTP %s %s",
                container, resp.status_code, resp.text[:200],
            )
            return False
        logger.info("Stopped daemon %s", container)
        return True
    except Exception as exc:
        logger.error("Failed to stop daemon %s: %s", container, exc)
        return False


__all__ = [
    "DOCKER_SOCKET",
    "container_state",
    "start_container",
    "stop_container",
]
