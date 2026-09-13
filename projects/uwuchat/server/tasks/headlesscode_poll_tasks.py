"""Headlesscode event-polling Celery tasks (Phase 4: relay).

Two tasks:

- ``trigger_headlesscode_session_polling`` (Celery Beat) enumerates
  every ``running`` row in ``headlesscode_sessions`` across tenant
  schemas and enqueues one ``poll_headlesscode_session_task`` per
  session — mirroring ``periodic_tasks.trigger_all_connected``: Beat
  stays lightweight, and the per-session tasks are individually
  visible and isolated from each other's failures.
- ``poll_headlesscode_session_task`` polls one session's event feed
  (``GET /api/session/:id/events?since=<event_offset>``), persists new
  rows to ``headlesscode_session_events`` with their ``turn``/``system``
  grouping, advances ``event_offset``, drives the session status
  (paused/resumed/terminal), settles the real cost via
  ``finalize_session_usage`` on terminal states, and appends everything
  new to the Redis outbox that ``headlesscode_ws_forwarder`` drains
  into the ``/api/v1/events`` WebSocket channel.

The poll task deliberately does not ``task.retry`` on transient HTTP
failures: the Beat trigger re-enqueues every running session every
couple of seconds anyway, so a retry would only triple the poll volume
during a dashboard outage instead of recovering faster. The per-session
helpers live in ``headlesscode_polling``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from airunner_services.tasks.celery_app import app
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@app.task(
    bind=True,
    name=(
        "projects.uwuchat.server.tasks.headlesscode_poll_tasks."
        "trigger_headlesscode_session_polling"
    ),
)
def trigger_headlesscode_session_polling(self) -> dict:
    """Enqueue a poll task for every running headlesscode session.

    Runs on the Beat schedule (see ``periodic_tasks``); the actual
    polling runs in ``poll_headlesscode_session_task`` on the default
    queue, so one slow session cannot block the others. An unreachable
    tenant is logged and skipped, never fatal.
    """
    from airunner_services.data.tenant import (
        tenant_key_from_schema,
        tenant_scope,
    )

    schemas = _list_tenant_schemas()
    if not schemas:
        return {"enqueued": 0}

    enqueued = 0
    for schema in schemas:
        tenant_key = tenant_key_from_schema(schema)
        if not tenant_key:
            continue
        try:
            with tenant_scope(tenant_key):
                enqueued += _enqueue_running_sessions(tenant_key)
        except Exception as exc:
            logger.warning(
                "Headlesscode poll trigger: skipping tenant %s: %s",
                tenant_key, exc,
            )
    logger.info("Headlesscode poll trigger: enqueued %d", enqueued)
    return {"enqueued": enqueued}


@app.task(
    bind=True,
    name=(
        "projects.uwuchat.server.tasks.headlesscode_poll_tasks."
        "poll_headlesscode_session_task"
    ),
)
def poll_headlesscode_session_task(
    self, session_id: int, tenant_key: str,
) -> dict:
    """Poll one running headlesscode session's event feed."""
    from airunner_services.data.tenant import tenant_scope

    with tenant_scope(tenant_key):
        try:
            return _poll_session(session_id)
        except Exception:
            logger.exception(
                "Headlesscode poll failed for session %d", session_id,
            )
            return {"status": "error", "reason": "exception"}


def _poll_session(session_id: int) -> dict:
    """Fetch, persist, and forward one session's new events."""
    from airunner_services.database.session import session_scope

    from projects.uwuchat.server.headlesscode_polling import (
        apply_status_transitions,
        forward_new,
        load_session_context,
        persist_new_events,
        safe_next_offset,
    )

    with session_scope() as session:
        context = load_session_context(session, session_id)
        if context[0] is None:
            return _unpollable_result(context[1])
        row, project = context
        new_events, next_offset = _fetch_events(row, project.workspace_root)
        new_kinds = persist_new_events(session, row, new_events)
        status_change, terminal_cost = apply_status_transitions(
            row, new_events,
        )
        row.event_offset = safe_next_offset(
            next_offset, row.event_offset, session_id,
        )
        snapshot = {
            "row_id": row.id,
            "hc_session_id": row.headlesscode_session_id,
            "status": row.status,
            "account_id": project.user_id,
        }
        session.commit()

    # snapshot carries every value used post-commit (session_scope
    # expires + detaches the ORM instances on exit).
    forward_new(
        snapshot["account_id"], snapshot, new_events, new_kinds,
        status_change,
    )
    _settle_terminal_cost(snapshot["account_id"], snapshot, terminal_cost)
    return {"status": "ok", "events": len(new_events)}


def _unpollable_result(reason: str) -> dict:
    """Map a load-failure reason to a poll task result.

    A vanished or quiet session is an expected ``noop``; a session
    whose project is gone is an anomaly worth surfacing as ``error``.
    """
    status = "error" if reason == "project_missing" else "noop"
    return {"status": status, "reason": reason}


def _fetch_events(row: Any, repo_path: str) -> tuple[list[dict], int]:
    """Return ``(new_events, raw_next_offset)`` for one session poll."""
    from projects.uwuchat.server.headlesscode_client import (
        get_session_events,
    )
    from projects.uwuchat.server.tasks.headlesscode_tasks import (
        _run_async,
    )

    response = _run_async(get_session_events(
        row.headlesscode_session_id, repo_path, since=row.event_offset,
    ))
    new_events = response.get("events") or []
    return new_events, response.get("nextOffset")


def _settle_terminal_cost(
    account_id: int, snapshot: dict, terminal_cost: Decimal | None,
) -> None:
    """Debit a finished session's real cost, idempotently."""
    if terminal_cost is None:
        return
    from projects.uwuchat.server.tasks.headlesscode_tasks import (
        finalize_session_usage,
    )

    finalize_session_usage(
        account_id, snapshot["hc_session_id"], terminal_cost,
    )


def _enqueue_running_sessions(tenant_key: str) -> int:
    """Enqueue one poll task per active session in the tenant.

    "Active" means ``running`` or ``paused`` — a paused session must
    keep being polled or it would never observe the ``resumed`` event
    that brings it back to ``running``.
    """
    from airunner_services.database.session import session_scope

    from projects.uwuchat.server.models.headlesscode_session import (
        HeadlesscodeSession,
        HeadlesscodeSessionStatus,
    )

    active = [
        HeadlesscodeSessionStatus.RUNNING.value,
        HeadlesscodeSessionStatus.PAUSED.value,
    ]
    with session_scope() as session:
        rows = (
            session.query(HeadlesscodeSession.id)
            .filter(
                HeadlesscodeSession.status.in_(active),
                HeadlesscodeSession.deleted == False,
            )
            .all()
        )
        if not rows:
            return 0

        for (session_id,) in rows:
            poll_headlesscode_session_task.apply_async(
                args=[session_id, tenant_key],
            )
        return len(rows)


def _list_tenant_schemas() -> list[str]:
    """Return all tenant schema names from the public database."""
    from airunner_services.database.session import public_session_scope
    from sqlalchemy import text

    try:
        with public_session_scope() as session:
            result = session.execute(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name LIKE 'tenant_%'",
                ),
            )
            return [row[0] for row in result.fetchall()]
    except Exception as exc:
        logger.warning("Failed to list tenant schemas: %s", exc)
        return []
