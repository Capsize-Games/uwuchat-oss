"""UwUChat Celery tasks — project-level task definitions.

Framework-level task infrastructure lives in
``airunner_services.tasks``.  Tasks in this package are specific
to UwUChat and are registered via the centralized routing table
in ``airunner_services.tasks.celery_app``.

Exports:
  periodic_tasks   — Celery Beat scheduled tasks (email sync trigger)
  email_tasks      — email sync task definitions
"""
