"""GPU inference-mode switcher — local-dev daemon arbitration.

When code mode toggles, exactly one of the two local GGUF daemons must
be loaded on the shared RTX 5080 (16GB VRAM):

| Code mode | DIALOGUE (main chat)            | GPU state                    |
|-----------|----------------------------------|------------------------------|
| ON        | code daemon (Qwen3-14B)          | code daemon loaded           |
| OFF       | chat daemon (e.g. Qwen3.5-9B)    | chat daemon loaded           |

Chat and code models are independently configurable (see
``dialogue_routing`` for the chat side, ``HEADLESSCODE_OLLAMA_URL`` for
the code side). When both point at the SAME daemon container — e.g. the
Qwen3-14B coder daemon serving both DIALOGUE and code mode — the switch
is a no-op: there is nothing to arbitrate, and stopping/starting a
single container would needlessly drop the model both modes share.

Mechanism: docker stop/start on the two daemon containers via the Docker
Engine API over the mounted unix socket — see
``projects/uwuchat/server/daemon_docker_client.py`` for the low-level
client and plans/uwuchat-code-mode-gpu-model-switching.md Decision A for
why the daemons' native HTTP /unload APIs are unusable (they return
success while leaving VRAM untouched — verified live).

The HTTP/docker calls are isolated in ``daemon_docker_client`` so this
module stays unit-testable with ``unittest.mock.patch`` on exactly those
functions (matching the codebase's established test style).
"""

from __future__ import annotations

import logging
import os
import time

import httpx

from projects.uwuchat.server.daemon_docker_client import (
    start_container as _start_container,
)
from projects.uwuchat.server.daemon_docker_client import (
    stop_container as _stop_container,
)

logger = logging.getLogger(__name__)

# Container names of the two daemons (must match the compose projects in
# deploy/local/daemons/). Both env-overridable so a shared single daemon
# config (chat == code) can point at one container.
CHAT_DAEMON_CONTAINER = os.getenv(
    "UWUCHAT_CHAT_DAEMON_CONTAINER", "lan-daemon-daemon-1"
)
CODE_DAEMON_CONTAINER = os.getenv(
    "UWUCHAT_CODE_DAEMON_CONTAINER", "code-daemon-daemon-1"
)

# Host ports each daemon publishes (for the readiness probe).
CHAT_DAEMON_PORT = 11434
CODE_DAEMON_PORT = 11435

# How long to wait for a daemon's ollama-compat /api/tags to come up
# after a container start (model load happens lazily on first request,
# so this only checks the HTTP server is reachable).
_READY_TIMEOUT_SECONDS = 180.0
_READY_POLL_INTERVAL = 2.0


def daemon_ready(container: str) -> bool:
    """Return whether *container*'s ollama-compat API is reachable.

    The probe uses the container name over the shared compose network
    (the same way DIALOGUE's ollama provider reaches the daemon) — NOT
    127.0.0.1, which from inside the server/celery netns would be the
    container itself, not the host-published port.

    The daemon is launched with ``--no-preload`` so the GGUF loads
    lazily on the first request; this only proves the HTTP server is up,
    which is sufficient for the switch to hand control back.
    """
    url = os.getenv(
        "UWUCHAT_DAEMON_BASE_URL", f"http://{container}:11434"
    )
    try:
        resp = httpx.get(f"{url}/api/tags", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


def _same_daemon() -> bool:
    """Return whether the chat and code daemons are the same container.

    When chat and code share one daemon (e.g. Qwen3-14B serving both),
    there is nothing to arbitrate — toggling code mode must not stop
    the container both modes depend on.
    """
    return (
        CHAT_DAEMON_CONTAINER == CODE_DAEMON_CONTAINER
    )


def apply_code_mode(enabled: bool) -> bool:
    """Ensure the GPU daemons match *enabled* (code-mode state).

    Code mode ON  → code daemon running, chat daemon stopped.
    Code mode OFF → chat daemon running, code daemon stopped.

    When the chat and code daemons are the SAME container (chat and code
    use the same model/daemon), this is a no-op — the single daemon stays
    running for both modes. Returns True in that case (the desired state
    is trivially satisfied).

    Returns True when the target state is reached (or was already the
    state). Never raises.
    """
    if _same_daemon():
        logger.info(
            "Chat and code share daemon %s — no GPU switch",
            CHAT_DAEMON_CONTAINER,
        )
        return True
    if enabled:
        _stop_container(CHAT_DAEMON_CONTAINER)
        if _start_container(CODE_DAEMON_CONTAINER) and _wait_for_daemon(
            CODE_DAEMON_CONTAINER
        ):
            logger.info("GPU inference mode set to code")
            return True
        return False

    _stop_container(CODE_DAEMON_CONTAINER)
    if _start_container(CHAT_DAEMON_CONTAINER) and _wait_for_daemon(
        CHAT_DAEMON_CONTAINER
    ):
        logger.info("GPU inference mode set to chat")
        return True
    return False


def _wait_for_daemon(container: str) -> bool:
    """Poll the daemon's API until it is ready or the timeout passes."""
    deadline = time.monotonic() + _READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if daemon_ready(container):
            return True
        time.sleep(_READY_POLL_INTERVAL)
    logger.error(
        "Daemon %s not ready within %ds",
        container, int(_READY_TIMEOUT_SECONDS),
    )
    return False


def current_mode_description() -> str:
    """Return a short human-readable description of the GPU state."""
    chat_state = _container_state(CHAT_DAEMON_CONTAINER)
    code_state = _container_state(CODE_DAEMON_CONTAINER)
    vram = gpu_vram_mib()
    return (
        f"chat_daemon={chat_state} code_daemon={code_state} "
        f"vram_used_mib={vram}"
    )


def _container_state(container: str) -> str | None:
    """Return the container's running state, or None (never raises)."""
    from projects.uwuchat.server.daemon_docker_client import (
        container_state,
    )

    try:
        return container_state(container)
    except Exception:
        return None


def gpu_vram_mib() -> int | None:
    """Return the GPU's used VRAM in MiB via nvidia-smi, or None.

    Local-dev diagnostics only — the switcher itself does not depend on
    this (VRAM is the *verification* signal, not the control signal).
    """
    import shutil
    import subprocess

    if shutil.which("nvidia-smi") is None:
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=10.0, check=False,
        )
        value = out.stdout.strip()
        if not value:
            return None
        return int(float(value.replace("MiB", "").strip()))
    except Exception:
        return None


__all__ = [
    "CHAT_DAEMON_CONTAINER",
    "CHAT_DAEMON_PORT",
    "CODE_DAEMON_CONTAINER",
    "CODE_DAEMON_PORT",
    "_same_daemon",
    "apply_code_mode",
    "current_mode_description",
    "daemon_ready",
    "gpu_vram_mib",
]
