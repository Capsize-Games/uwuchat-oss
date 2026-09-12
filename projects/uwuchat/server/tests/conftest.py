"""Shared fixtures for UwUchat server tests."""

from __future__ import annotations

import os

import pytest

from airunner_services.database.session import reset_engine
from airunner_services.database.setup_database import setup_database


@pytest.fixture()
def _db(monkeypatch: pytest.MonkeyPatch) -> str:
    """Ensure the test database is reachable and the public schema is
    initialised."""
    db_url = os.environ.get(
        "AIRUNNER_TEST_DATABASE_URL",
        os.environ.get("AIRUNNER_DATABASE_URL"),
    )
    if not db_url:
        pytest.skip(
            "No test database configured (AIRUNNER_TEST_DATABASE_URL)"
        )
    if not db_url.startswith("postgres"):
        pytest.skip("UwUchat server tests require PostgreSQL")
    monkeypatch.setenv("AIRUNNER_DATABASE_URL", db_url)
    monkeypatch.setenv("AIRUNNER_DISABLE_DB_SETUP_CACHE", "1")
    reset_engine()
    try:
        setup_database()
    except Exception as exc:
        pytest.skip(f"Database unavailable: {exc}")
    return db_url
