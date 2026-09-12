"""Verify every Celery task module is actually importable at worker
startup, not just registered as a route.

Regression coverage: ``celery_app.py`` previously configured
``task_routes`` for several modules (email sync, downloads, RAG,
knowledge extraction) without an ``include=`` list. A route entry
only affects where an *already-registered* task is queued — it does
not import the module, so ``@app.task`` never ran and
``apply_async()`` silently enqueued messages no worker had a handler
for. This was the actual root cause behind the email sync progress
bar never appearing: the sync task never executed at all.
"""

from __future__ import annotations

import importlib.util


class TestTaskIncludeList:
    """``_task_include_list`` must name every module task_routes
    references, so celery -A ... worker actually imports it."""

    def test_includes_all_framework_task_modules(self) -> None:
        from airunner_services.tasks.celery_app import (
            _task_include_list,
        )

        modules = _task_include_list()
        assert "airunner_services.tasks.download_tasks" in modules
        assert "airunner_services.tasks.rag_tasks" in modules
        assert "airunner_services.tasks.knowledge_tasks" in modules

    def test_includes_uwuchat_email_modules_when_project_present(
        self,
    ) -> None:
        from airunner_services.tasks.celery_app import (
            _task_include_list,
        )

        modules = _task_include_list()
        has_uwuchat = importlib.util.find_spec(
            "projects.uwuchat.server.tasks.email_tasks",
        )
        if has_uwuchat is not None:
            assert (
                "projects.uwuchat.server.tasks.email_tasks" in modules
            )
            assert (
                "projects.uwuchat.server.tasks.email_indexing_tasks"
                in modules
            )
            assert (
                "projects.uwuchat.server.tasks.periodic_tasks"
                in modules
            )


class TestTaskModulesRegisterOnImport:
    """Importing each included module must actually register its
    ``@app.task`` functions on the shared Celery app."""

    def test_email_tasks_register(self) -> None:
        importlib.import_module(
            "projects.uwuchat.server.tasks.email_tasks",
        )
        from airunner_services.tasks.celery_app import app

        assert (
            "projects.uwuchat.server.tasks.email_tasks"
            ".sync_email_account" in app.tasks
        )
        assert (
            "projects.uwuchat.server.tasks.email_tasks"
            "._sync_one_mailbox" in app.tasks
        )
        assert (
            "projects.uwuchat.server.tasks.email_tasks"
            "._sync_callback" in app.tasks
        )

    def test_download_tasks_register(self) -> None:
        importlib.import_module("airunner_services.tasks.download_tasks")
        from airunner_services.tasks.celery_app import app

        assert (
            "airunner_services.tasks.download_tasks"
            ".huggingface_download" in app.tasks
        )
