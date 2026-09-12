"""Regression test: Celery Beat schedule must not silently end up
empty.

Found live while dogfooding UwUChat's code mode: a launched
headlesscode session never left "running" because
_build_beat_schedule()'s import path
(``projects.{project}.server.periodic_tasks``) didn't match where
periodic_tasks.py actually lives
(``projects.uwuchat.server.tasks.periodic_tasks``) — the mismatch was
swallowed by a bare ``except ImportError: pass``, so beat_schedule
silently stayed ``{}`` and NOTHING periodic (email sync, headlesscode
polling) ever ran, in any deployment.
"""

from __future__ import annotations

from unittest.mock import patch

from airunner_services.tasks.celery_app import _build_beat_schedule


def test_uwuchat_beat_schedule_is_not_empty() -> None:
    with patch(
        "airunner_services.tasks.celery_app._active_project",
        return_value="uwuchat",
    ):
        schedule = _build_beat_schedule()
    assert schedule, (
        "beat_schedule is empty — periodic_tasks.py failed to import "
        "(see this test's docstring for the exact bug this catches)"
    )


def test_uwuchat_beat_schedule_has_headlesscode_poll_entry() -> None:
    with patch(
        "airunner_services.tasks.celery_app._active_project",
        return_value="uwuchat",
    ):
        schedule = _build_beat_schedule()
    assert "poll-headlesscode-running-sessions" in schedule
    entry = schedule["poll-headlesscode-running-sessions"]
    assert entry["task"] == (
        "projects.uwuchat.server.tasks.headlesscode_poll_tasks."
        "trigger_headlesscode_session_polling"
    )


def test_uwuchat_beat_schedule_has_email_sync_entry() -> None:
    with patch(
        "airunner_services.tasks.celery_app._active_project",
        return_value="uwuchat",
    ):
        schedule = _build_beat_schedule()
    assert "trigger-email-sync-all-tenants" in schedule


def test_no_active_project_returns_empty_schedule() -> None:
    with patch(
        "airunner_services.tasks.celery_app._active_project",
        return_value="",
    ):
        schedule = _build_beat_schedule()
    assert schedule == {}
