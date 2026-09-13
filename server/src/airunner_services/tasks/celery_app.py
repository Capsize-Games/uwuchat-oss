"""Celery application skeleton for airunner background tasks.

Centralized task-routing and queue definitions mirror fastsearch's
proven per-queue isolation pattern, but with explicit resource
limits and per-environment configuration via env vars.
"""

from __future__ import annotations

import importlib
import importlib.util
import os

from celery import Celery

# -- Config from environment ------------------------------------------------

_BROKER_URL = os.environ.get(
    "AIRUNNER_CELERY_BROKER_URL",
    "redis://airunner-redis:6379/0",
)
_RESULT_BACKEND_URL = os.environ.get(
    "AIRUNNER_CELERY_RESULT_BACKEND_URL",
    "redis://airunner-redis:6379/1",
)

# -- Task module registration ------------------------------------------------


def _active_project() -> str:
    """Return the active ``AIRUNNER_PROJECT`` (env, then settings)."""
    project = os.environ.get("AIRUNNER_PROJECT", "")
    if project:
        return project
    try:
        from airunner_services.conf import settings

        return getattr(settings, "AIRUNNER_PROJECT", "") or ""
    except Exception:
        return ""


def _task_include_list() -> list[str]:
    """Return the dotted module paths every worker must import.

    A Celery ``@app.task`` decorator only registers the task when its
    module is actually imported. ``celery -A ... worker`` imports only
    this module (plus whatever it imports at module level), so without
    an explicit ``include=``, task modules that nothing else imports
    are silently unregistered — ``apply_async()`` still enqueues the
    message, but no worker has a handler for it and the task never
    runs. Project modules are guarded by try/except, mirroring
    ``_build_beat_schedule()``, so the framework doesn't hard-depend
    on any specific project.

    Only the active project's task modules are imported — a project
    defines its own model classes over its own tables, so importing
    another project's task modules in one process risks a SQLAlchemy
    ``InvalidRequestError`` on a shared table name.
    """
    modules = [
        "airunner_services.tasks.download_tasks",
        "airunner_services.tasks.rag_tasks",
        "airunner_services.tasks.knowledge_tasks",
    ]
    project = _active_project()
    if project == "uwuchat":
        project_modules = [
            "projects.uwuchat.server.tasks.email_tasks",
            "projects.uwuchat.server.tasks.email_indexing_tasks",
            "projects.uwuchat.server.tasks.periodic_tasks",
            "projects.uwuchat.server.tasks.headlesscode_tasks",
            "projects.uwuchat.server.tasks.headlesscode_poll_tasks",
            "projects.uwuchat.server.tasks.random_chatbot_tasks",
            "projects.uwuchat.server.tasks.gpu_inference_tasks",
        ]
    else:
        project_modules = []
    for name in project_modules:
        try:
            found = importlib.util.find_spec(name) is not None
        except ModuleNotFoundError:
            found = False
        if found:
            modules.append(name)
    return modules


# -- Celery app -------------------------------------------------------------

app = Celery(
    "airunner",
    broker=_BROKER_URL,
    backend=_RESULT_BACKEND_URL,
    include=_task_include_list(),
)

# Standard config.  These can be overridden via env in the worker
# compose service's ``command:`` or ``environment:`` sections.
app.conf.update(
    # Timezone for Beat schedules and task timestamps.
    timezone="UTC",
    enable_utc=True,
    # Acknowledge tasks only after execution, not on receipt, so a
    # worker crash re-queues in-flight work (at-most-once delivery
    # would silently drop it).
    task_acks_late=True,
    # Limit the number of un-acked tasks per worker prefetch so one
    # slow task cannot starve other workers.
    worker_prefetch_multiplier=1,
    # Explicit task routing — add new task routes here rather than
    # passing ``queue=`` at each call site (centralized, reviewable).
    task_routes={
        # Email sync: dedicated queue so one user's large mailbox
        # backfill cannot starve everyone else's quick tasks.
        "airunner_services.tasks.email_tasks.*": {"queue": "sync"},
        # UwUChat project email-sync tasks use the same sync queue.
        "projects.uwuchat.server.tasks.email_tasks.*": {"queue": "sync"},
        # Periodic sync trigger: runs on Beat but enqueues onto
        # the sync queue so a sync-dedicated worker picks it up.
        "projects.uwuchat.server.tasks.periodic_tasks.*": {
            "queue": "sync",
        },
        # Download jobs: isolated queue so model/file downloads
        # don't block short-lived tasks.
        "airunner_services.tasks.download_tasks.*": {
            "queue": "downloads",
        },
        # Everything else (RAG, knowledge extraction, curiosity,
        # interjection) → default queue.
        "airunner_services.tasks.rag_tasks.*": {"queue": "default"},
        "airunner_services.tasks.knowledge_tasks.*": {"queue": "default"},
        # Headlesscode session lifecycle (launch + polling). Without
        # an explicit route these fall through to Celery's built-in
        # default queue name ("celery"), which no worker in this
        # stack listens on ("-Q default,downloads[,sync]") — the task
        # is accepted by the broker and then silently never runs.
        # Verified live 2026-08-20: a confirmed launch returned
        # "Started a headlesscode session" to the user, but the
        # Celery worker never logged receiving the task and no
        # headlesscode_sessions row was ever written.
        "projects.uwuchat.server.tasks.headlesscode_tasks.*": {
            "queue": "default",
        },
        "projects.uwuchat.server.tasks.headlesscode_poll_tasks.*": {
            "queue": "default",
        },
        # GPU inference-mode switch (code-mode toggle daemon arbitration):
        # runs on the default queue — it's short (docker stop/start) and
        # must not share the email-sync queue with long mailbox backfills.
        "projects.uwuchat.server.tasks.gpu_inference_tasks.*": {
            "queue": "default",
        },
    },
    # Worker concurrency — override via AIRUNNER_CELERY_CONCURRENCY env.
    worker_concurrency=int(
        os.environ.get("AIRUNNER_CELERY_CONCURRENCY", "2"),
    ),
    # Result expiry: keep task results for 1 hour (debugging only).
    result_expires=3600,
    # Beat schedule: populated dynamically at worker-import time
    # via ``_build_beat_schedule()`` so project-level tasks can
    # register without coupling the framework to UwUChat.
    beat_schedule={},
)

# -- Queue isolation config (applied per-queue at worker startup) -----------

# Per-queue concurrency overrides (default worker handles all queues
# with the global worker_concurrency, but the sync-dedicated worker
# service overrides this via ``-c`` on its command line).
app.conf.task_queue_max_priority = 10
app.conf.task_default_priority = 5


def _build_beat_schedule() -> dict:
    """Return the Celery Beat schedule dictionary.

    Called by modules that register periodic tasks.  Kept here
    rather than inline in ``celery_app.py`` so the framework
    doesn't import project-specific modules unconditionally.  Only
    the active project's schedule module is imported.
    """
    schedule: dict = {}
    project = _active_project()
    if not project:
        return schedule

    try:
        mod = importlib.import_module(
            f"projects.{project}.server.tasks.periodic_tasks"
        )
        for name in ("PERIODIC_EMAIL_SYNC_SCHEDULE",
                     "PERIODIC_HEADLESSCODE_POLL_SCHEDULE"):
            entry = getattr(mod, name, None)
            if entry:
                schedule.update(entry)
    except ImportError:
        # Deliberately loud: an empty beat_schedule means EVERY
        # periodic task (email sync, headlesscode session polling)
        # silently never runs — this exact silent `pass` hid that for
        # a real stretch (the module path here didn't match where
        # periodic_tasks.py actually lives, under a `tasks/`
        # subpackage) until a live headlesscode session was dogfooded
        # and its status just never left "running".
        import logging

        logging.getLogger(__name__).error(
            "Beat schedule empty: projects.%s.server.tasks."
            "periodic_tasks failed to import — periodic tasks "
            "(email sync, headlesscode polling) will never run.",
            project,
            exc_info=True,
        )

    return schedule


# Freeze the schedule when this module is first loaded in a Beat
# process.  In a plain worker process this is harmless — the dict
# is consulted only by the Beat scheduler.
_app_schedule = _build_beat_schedule()
if _app_schedule:
    app.conf.beat_schedule = _app_schedule
