"""FastAPI application setup and server configuration."""

from __future__ import annotations

import asyncio
import importlib
import os
from contextlib import asynccontextmanager
from ipaddress import ip_address
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from airunner_services.runtimes.bootstrap import build_runtime_registry
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

from .server_helpers import (
    _mount_static_files,
    _register_watchers,
    _setup_registry_and_lifecycle,
    _setup_signal_bridges,
)
from .server_middleware import (
    register_exception_handler,
    register_middleware,
    update_api_key_config,
)
from .server_routes import register_routes
from .server_sentry import init_sentry

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


def access_logs_enabled() -> bool:
    """Return whether uvicorn access logs should be emitted."""
    return os.environ.get("AIRUNNER_API_ACCESS_LOG", "0") == "1"


def _resolve_runtime_registry(app_instance: Any) -> Optional[Any]:
    """Return or create the runtime registry for an app instance."""
    registry = getattr(app_instance, "runtime_registry", None)
    if registry is not None:
        return registry
    try:
        registry = build_runtime_registry(app_instance=app_instance)
    except Exception:
        logger.exception("Failed to build runtime registry")
        return None
    try:
        setattr(app_instance, "runtime_registry", registry)
    except Exception:
        logger.debug("Unable to attach runtime registry to app instance")
    return registry


def _resolve_lifecycle_service(app_instance: Any) -> Optional[Any]:
    """Return the lifecycle service attached to an app instance."""
    return getattr(app_instance, "lifecycle_service", None)


_BEHIND_PROXY = os.environ.get("AIRUNNER_BEHIND_PROXY", "").strip() == "1"

_TRUSTED_PROXY_IPS_RAW = os.environ.get(
    "AIRUNNER_TRUSTED_PROXY_IPS", "127.0.0.1,::1"
).strip()
_TRUSTED_PROXY_IPS: set[str] = {
    ip.strip()
    for ip in _TRUSTED_PROXY_IPS_RAW.split(",")
    if ip.strip()
}


def is_loopback_host(host: str) -> bool:
    """Return whether *host* resolves to a loopback address."""
    if not host:
        return False
    normalized = host.strip().lower()
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _real_client_ip(request: Request) -> str:
    """Return the real client IP, accounting for a trusted reverse proxy.

    When ``AIRUNNER_BEHIND_PROXY=1``, the immediate TCP peer
    (``request.client.host``) is checked against
    ``AIRUNNER_TRUSTED_PROXY_IPS``.  Forwarded headers are **only**
    trusted when the peer is itself a known proxy — a direct connection
    that happens to carry ``X-Real-IP: 127.0.0.1`` is never treated as
    loopback.

    When the proxy peer is trusted, ``X-Real-IP`` is preferred,
    falling back to the rightmost entry in ``X-Forwarded-For`` (closest
    to the proxy, hardest for a remote attacker to spoof).  Every
    extracted value is validated as a well-formed IP address before it
    is trusted.

    When the env var is not set, or the immediate peer is not a
    trusted proxy, returns the raw TCP peer address — preserving
    the existing behaviour for deployments that do not sit behind a
    reverse proxy.
    """
    client = getattr(request, "client", None)
    direct_ip = getattr(client, "host", "") if client else ""

    if not _BEHIND_PROXY:
        return direct_ip

    # Only trust forwarded headers when the immediate TCP peer is a
    # known trusted proxy.  A direct connection that carries spoofed
    # X-Real-IP / X-Forwarded-For headers must not be trusted.
    if direct_ip not in _TRUSTED_PROXY_IPS:
        return direct_ip

    # Prefer X-Real-IP (single-hop proxy) when it is a valid IP.
    x_real_ip = (request.headers.get("X-Real-IP") or "").strip()
    if x_real_ip:
        try:
            ip_address(x_real_ip)
            return x_real_ip
        except ValueError:
            pass

    # Fall back to the rightmost X-Forwarded-For entry.
    xff = (request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        for candidate in reversed(
            [entry.strip() for entry in xff.split(",")]
        ):
            if not candidate:
                continue
            try:
                ip_address(candidate)
                return candidate
            except ValueError:
                continue

    # No valid forwarded header — return the proxy's own IP (which is
    # in the trusted set and therefore known to be a proxy, not a real
    # client, so is_loopback_request will correctly return False).
    return direct_ip


def is_loopback_request(request: Request) -> bool:
    """Return whether the request originated from a loopback address.

    Proxy-aware — when ``AIRUNNER_BEHIND_PROXY=1`` the real client IP
    is extracted from ``X-Real-IP`` / ``X-Forwarded-For`` rather than
    from the raw TCP peer (which is always the proxy's own address).
    """
    return is_loopback_host(_real_client_ip(request))


async def _sync_catalog_on_startup() -> None:
    """Sync the OpenRouter model pricing catalog in the background.

    Runs as a startup task so cost estimates are accurate from the
    first request.  Failures are logged but never block startup.
    """
    try:
        from airunner_services.llm.openrouter_catalog import sync_catalog

        loop = asyncio.get_running_loop()
        count = await loop.run_in_executor(None, sync_catalog)
        logger.info(
            "OpenRouter catalog startup sync complete: %d models", count
        )
    except Exception:
        logger.warning(
            "OpenRouter catalog startup sync failed", exc_info=True
        )


def _start_headlesscode_ws_forwarder() -> asyncio.Task | None:
    """Start UwUchat's headlesscode WS forwarder, or None if absent.

    The Celery worker cannot reach this process's ``WsEventBus``, so a
    forwarder here drains the Redis outbox into ``/api/v1/events``.
    ImportError-guarded so the framework boots without the project.
    """
    try:
        module = importlib.import_module(
            "projects.uwuchat.server.headlesscode_ws_forwarder"
        )
        return module.start_headlesscode_ws_forwarder()
    except ImportError:
        logger.info("Headlesscode WS forwarder unavailable -- skipping")
        return None


def _start_uwu_creation_ws_forwarder() -> asyncio.Task | None:
    """Start the UwUchat uwu_creation WS forwarder, or None if absent.

    Mirrors the headlesscode forwarder: the Celery worker writing
    creation-status transitions cannot reach this process's
    ``WsEventBus``, so a forwarder here drains the Redis outbox into
    ``/api/v1/events``.  ImportError-guarded so the framework boots
    without the UwUChat project.
    """
    try:
        from projects.uwuchat.server.uwu_creation_ws_forwarder import (
            start_uwu_creation_ws_forwarder,
        )

        return start_uwu_creation_ws_forwarder()
    except ImportError:
        logger.info(
            "uwu_creation WS forwarder unavailable -- skipping"
        )
        return None


async def _stop_background_task(task: asyncio.Task | None) -> None:
    """Cancel and await a background task, ignoring cancellation."""
    if task is None:
        return
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown tasks."""
    logger.info("FastAPI server starting...")
    hardware_task = None
    try:
        from airunner_services.api.routes.hardware_broadcast import (
            start_hardware_broadcast,
        )

        hardware_task = start_hardware_broadcast()
    except ImportError:
        logger.info("Hardware broadcast unavailable -- skipping")

    headlesscode_forwarder_task = _start_headlesscode_ws_forwarder()
    uwu_creation_forwarder_task = _start_uwu_creation_ws_forwarder()

    # Sync OpenRouter model pricing catalog on startup so cost
    # estimates are accurate from the first request.
    _ = asyncio.create_task(_sync_catalog_on_startup())

    # Register email sync signal handler so EMAIL_START_SYNC
    # enqueues Celery tasks when the connect route fires it.
    # (The periodic scheduler is now a Celery Beat task — see
    # projects/uwuchat/server/tasks/periodic_tasks.py.)
    try:
        from projects.uwuchat.server.email.sync_engine import (
            register_signals,
        )

        register_signals()
    except ImportError:
        logger.info("Email sync signals unavailable -- skipping")

    try:
        from projects.uwuchat.server.embedding_recovery import (
            register_signals as register_embedding_signals,
        )

        register_embedding_signals()
    except ImportError:
        logger.info(
            "Embedding recovery signals unavailable -- skipping"
        )

    try:
        yield
    finally:
        logger.info("FastAPI server shutting down...")
        await _stop_background_task(hardware_task)
        await _stop_background_task(headlesscode_forwarder_task)
        await _stop_background_task(uwu_creation_forwarder_task)


def _default_allowed_origins() -> list[str]:
    """Return CORS origins from env, or sensible defaults per deployment mode."""
    env_origins = os.environ.get("AIRUNNER_ALLOWED_ORIGINS", "").strip()
    if env_origins:
        return [o.strip() for o in env_origins.split(",") if o.strip()]
    mode = os.environ.get("AIRUNNER_DEPLOYMENT_MODE", "development").lower()
    if mode == "production":
        return []  # Must be set explicitly via AIRUNNER_ALLOWED_ORIGINS
    # Development mode: empty list signals "allow all loopback ports"
    return []


def _setup_cors(
    app: FastAPI,
    allowed_origins: Optional[list],
    enable_cors: bool,
) -> None:
    """Apply CORS middleware to the app."""
    if not enable_cors:
        return
    origins = (
        allowed_origins
        if allowed_origins is not None
        else _default_allowed_origins()
    )
    mode = os.environ.get("AIRUNNER_DEPLOYMENT_MODE", "development").lower()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    elif mode == "production":
        logger.warning(
            "CORS is enabled but AIRUNNER_ALLOWED_ORIGINS is not set. "
            "Set it to your frontend domain(s) in production."
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # Development mode: allow any localhost or 127.0.0.1 origin
        # on any port so multiple agent client instances can coexist
        app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=(r"https?://(localhost|127\.0\.0\.1)(:\d+)?"),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )


def _load_and_apply_extensions(app: FastAPI) -> None:
    """Load extensions and apply server hooks (no-op when empty)."""
    from airunner_services.extensions.loader import (
        load_extensions,
        apply_server_hooks,
    )

    load_extensions()
    apply_server_hooks(app)


def create_app(
    allowed_origins: Optional[list] = None,
    enable_cors: bool = True,
    app_instance: Optional[Any] = None,
) -> FastAPI:
    """Create and configure a FastAPI application instance."""
    init_sentry()
    _check_fhe_startup()
    app = FastAPI(
        title="AI Runner API",
        version="1.0.0",
        docs_url="/docs",
        lifespan=lifespan,
    )
    app.state.runtime_registry = None
    app.state.lifecycle_service = None
    _setup_registry_and_lifecycle(app, app_instance)
    _setup_signal_bridges(app_instance)
    update_api_key_config()
    _setup_cors(app, allowed_origins, enable_cors)
    # Load extensions before starting watchers: the object_storage extension's
    # ready() hook disables filesystem ingestion, and _register_watchers must
    # observe that to skip starting the directory watchers in prod.
    _load_and_apply_extensions(app)
    _register_watchers(app_instance)
    register_middleware(app)
    register_routes(app)
    _mount_static_files(app)
    register_exception_handler(app)
    return app


def _check_fhe_startup() -> None:
    """Run FHE availability check early, after logging is configured.

    This check is unconditional (no feature-flag gate — see
    :func:`check_fhe_available`).  If TenSEAL is missing, a CRITICAL
    log entry is emitted so the misconfiguration is impossible to
    miss.  The server is not prevented from booting — FHE search has
    a safe degrade path.
    """
    from airunner_services.utils.crypto.fhe_helpers import (
        check_fhe_available,
    )

    check_fhe_available()
