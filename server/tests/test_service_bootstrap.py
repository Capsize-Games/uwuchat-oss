"""Smoke tests for the service-owned daemon API bootstrap.

Verifies that the API server can be constructed and the FastAPI app
registers all expected routes without runtime model dependencies.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import ClassVar

# Ensure the services/src directory is on the path for
# the service-owned API imports.
_SERVICES_ROOT = Path(__file__).resolve().parents[1]
_PROJECT_ROOT = _SERVICES_ROOT.parent
_SERVICES_SRC = _PROJECT_ROOT / "services" / "src"

# Append paths (not prepend) to avoid shadowing site-packages.
# The services/src directory contains a 'requests/' package that would
# shadow the real requests library if placed earlier in sys.path.
_path_str = str(_SERVICES_SRC)
if _path_str not in sys.path:
    sys.path.append(_path_str)


class TestImportChain:
    """Verify that the service-owned API modules resolve."""

    def test_deleted_api_package_not_importable(self):
        """The removed top-level api package stays absent."""
        assert importlib.util.find_spec("airunner_api") is None

    def test_service_message_envelopes_are_self_owned(self):
        """Services resolve runtime envelope classes from their own module."""
        from airunner_services.ipc.messages import (
            EnvelopeStatus as ServiceStatus,
        )
        from airunner_services.runtimes.message_envelopes import (
            load_message_types,
        )

        assert ServiceStatus is load_message_types().EnvelopeStatus

    _SERVICE_API_IMPORTS: ClassVar[list[str]] = [
        "airunner_services.api.server",
        "airunner_services.api.routes.health",
        "airunner_services.api.routes.art_websocket",
        "airunner_services.api.routes.art_daemon_ws",
        "airunner_services.api.routes.art_runtime",
        "airunner_services.api.routes.llm_stream_routes",
        "airunner_services.api.routes.llm_runtime",
        "airunner_services.api.routes.llm_settings_presets",
        "airunner_services.api.routes.tts",
        "airunner_services.api.routes.daemon",
        "airunner_services.api.routes.events",
        "airunner_services.api.routes.canvas_document",
        "airunner_services.api.routes.hardware",
        "airunner_services.api.routes.geolocation",
    ]

    def test_import_service_api_server(self):
        """The service-owned API server module resolves."""
        importlib.import_module("airunner_services.api.server")

    def test_import_service_api_routes(self):
        """Every service-owned API route module resolves."""
        for path in self._SERVICE_API_IMPORTS:
            importlib.import_module(path)


EXPECTED_ROUTE_PREFIXES = [
    "/api/v1/health",
    "/api/v1/llm",
    "/api/v1/art",
    "/api/v1/tts",
    "/api/v1/daemon",
    "/api/v1/events",
    "/api/v1/canvas",
]


class TestFastAPIAppConstruction:
    """Verify that the FastAPI application can be constructed."""

    def test_create_app_returns_fastapi_instance(self):
        """create_app() returns a FastAPI application."""
        from airunner_services.api.server import create_app

        app = create_app(
            allowed_origins=["http://localhost"],
            enable_cors=True,
        )
        assert app is not None
        assert app.title == "AI Runner API"

    def test_all_expected_routes_registered(self):
        """The FastAPI app registers all expected route prefixes."""
        from airunner_services.api.server import create_app

        app = create_app(
            allowed_origins=["http://localhost"],
            enable_cors=True,
        )
        routes = {route.path for route in app.routes if hasattr(route, "path")}

        for prefix in EXPECTED_ROUTE_PREFIXES:
            found = any(route.startswith(prefix) for route in routes)
            assert (
                found
            ), f"Route prefix {prefix} not found in {sorted(routes)}"

    def test_root_endpoint(self, monkeypatch):
        """The root endpoint returns service info."""
        from airunner_services.api.server import create_app
        from fastapi.testclient import TestClient

        monkeypatch.setenv("AIRUNNER_INSECURE_NO_AUTH", "1")
        app = create_app(
            allowed_origins=["http://localhost"],
            enable_cors=True,
        )
        client = TestClient(app)
        # The root endpoint is the health check
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert "status" in body
