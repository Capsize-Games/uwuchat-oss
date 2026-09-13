"""Tests for admin Celery visibility endpoints.

Verifies superuser gating, degraded response on Celery inspection
timeout, and registered task-name reflection.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from airunner_services.api.routes.admin_celery_routes import router


@pytest.fixture()
def client_no_auth() -> TestClient:
    """Return a TestClient with the celery admin router, no auth."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin")
    return TestClient(app)


class TestCeleryWorkersEndpoint:
    """Tests for GET /api/v1/admin/celery/workers."""

    def test_workers_requires_auth(self, client_no_auth: TestClient):
        """Unathenticated requests are rejected."""
        response = client_no_auth.get("/api/v1/admin/celery/workers")
        assert response.status_code in (401, 403)

    def test_workers_degraded_on_inspect_timeout(self):
        """A slow/dead Celery inspect returns degraded, not 500."""
        # Test the endpoint logic directly by calling the handler
        # with a mocked Celery app that raises on inspect.
        from airunner_services.api.routes.admin_celery_routes import (
            celery_workers,
        )

        mock_app = MagicMock()
        mock_app.control.inspect.side_effect = TimeoutError("timed out")

        with patch(
            "airunner_services.tasks.celery_app.app",
            mock_app,
        ):
            import asyncio

            result = asyncio.run(
                celery_workers(
                    req=MagicMock(),
                    _account_id=1,
                )
            )

        assert "error" in result
        assert "unavailable" in result["error"].lower()
        assert result["workers"] == []

    def test_workers_reflects_registered_task_names(self):
        """Registered task names appear per worker."""
        from airunner_services.api.routes.admin_celery_routes import (
            celery_workers,
        )

        mock_app = MagicMock()
        mock_inspect = MagicMock()
        mock_inspect.stats.return_value = {
            "worker1@host": {"pool": {"max-concurrency": 4}},
        }
        mock_inspect.active.return_value = {"worker1@host": []}
        mock_inspect.reserved.return_value = {"worker1@host": []}
        mock_inspect.registered.return_value = {
            "worker1@host": [
                "sync_email_account",
                "index_email_bodies",
            ],
        }
        mock_app.control.inspect.return_value = mock_inspect

        with patch(
            "airunner_services.tasks.celery_app.app",
            mock_app,
        ):
            import asyncio

            result = asyncio.run(
                celery_workers(
                    req=MagicMock(),
                    _account_id=1,
                )
            )

        assert len(result["workers"]) == 1
        worker = result["workers"][0]
        assert "sync_email_account" in worker["registered_tasks"]
