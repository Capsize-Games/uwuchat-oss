"""Task queue (Celery) and caching (Redis) infrastructure.

Exports:
  celery_app       — shared Celery application instance
  redis_client     — Redis client wrapper keyed to DB indices
  task_helpers     — shared helpers for task-internal setup
"""
