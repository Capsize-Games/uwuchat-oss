"""Headlesscode session-lifecycle Celery tasks (Phase 3: launch).

``launch_headlesscode_session_task`` is enqueued by the
``launch_headlesscode_session`` tool. It calls the dashboard's
``POST /api/session/start`` via ``headlesscode_client`` and persists
the returned session id into ``headlesscode_sessions`` immediately —
the tool call itself stays fast, and the actual session lifecycle
runs entirely inside this task module (Phase 4 extends it with
polling).  ``finalize_session_usage`` is the completion handler that
debits a finished session's real cost, keyed by the real headlesscode
session id; Phase 4's polling loop drives it.

Phase 5: the task also appends a ``headlesscode_session`` card entry
to the launch conversation (via :mod:`headlesscode_card`) so the
client renders a live session card in the chat thread.

Retry safety: a Redis marker (keyed by the tool's idempotency_key,
computed once per user launch request) records a session id as soon
as ``start_session`` returns one, *before* persisting the DB row. If
persisting fails and Celery retries, the retry recovers the same
session id from the marker instead of calling ``start_session`` again
— so a DB hiccup after a real launch can't spawn a second billable
session. This does not cover the narrower race where the HTTP call to
``start_session`` itself times out after the dashboard already spawned
the session server-side (headlesscode's API has no client-supplied
idempotency key to de-duplicate that case) — a retry in that specific
window can still double-launch; this is a known residual risk.
"""

from __future__ import annotations

from decimal import Decimal

from airunner_services.tasks.celery_app import app
from airunner_services.tasks.redis_client import cache_redis
from celery.utils.log import get_task_logger

from projects.uwuchat.server.headlesscode_card import (
    append_session_card_entry,
)
from projects.uwuchat.server.models.headlesscode_session import (
    HeadlesscodeSessionStatus,
)

logger = get_task_logger(__name__)

_LAUNCH_MARKER_TTL_SECONDS = 3600


def _launch_marker_key(idempotency_key: str) -> str:
    return f"hc:launch-started:{idempotency_key}"


def _load_project_workspace_root(project_id: int) -> str | None:
    """Return the path sessions should actually run against, or None.

    ``workspace_root`` (not ``repo_path``) — a launch never operates
    on a project's primary checkout directly; ``workspace_root`` is
    the dashboard-resolved disposable worktree path, set at
    registration time (see headlesscode_service.py's
    ``_resolve_workspace_root``).
    """
    from airunner_services.database.session import session_scope

    from projects.uwuchat.server.models.headlesscode_project import (
        HeadlesscodeProject,
    )

    with session_scope() as session:
        project = session.query(HeadlesscodeProject).get(project_id)
        if project is None or project.deleted:
            return None
        return project.workspace_root


def _start_session_or_retry(
    task, project_id: int, repo_path: str, task_description: str,
    mode: str | None, idempotency_key: str,
) -> tuple[str, str | None]:
    """Call _recover_or_start_session, retrying the task on failure."""
    try:
        return _recover_or_start_session(
            repo_path, task_description, mode, idempotency_key,
        )
    except Exception:
        # Transient dashboard restarts are the realistic failure mode
        # here; retry a couple of times before giving up.
        logger.exception(
            "Headlesscode start_session failed for project %d",
            project_id,
        )
        raise task.retry(countdown=30, max_retries=2)


def _recover_or_start_session(
    repo_path: str, task_description: str, mode: str | None,
    idempotency_key: str,
) -> tuple[str, str | None]:
    """Return (session_id, resolved_mode), recovering a prior launch.

    Checking the marker first means a retry after a post-launch
    failure (e.g. the DB insert below) reuses the session headlesscode
    already started, instead of starting a second one. A recovered
    session has no cached response, so the resolved mode falls back
    to the originally-requested *mode*.
    """
    from projects.uwuchat.server.headlesscode_client import start_session

    marker_key = _launch_marker_key(idempotency_key)
    recovered = cache_redis().get(marker_key)
    if recovered:
        return recovered, mode

    response = _run_async(
        start_session(repo=repo_path, task=task_description, mode=mode)
    )
    session_id = str(response.get("sessionId") or "")
    if session_id:
        cache_redis().set(
            marker_key, session_id, ex=_LAUNCH_MARKER_TTL_SECONDS,
        )
    return session_id, (response.get("mode") or mode)


@app.task(
    bind=True,
    name=(
        "projects.uwuchat.server.tasks.headlesscode_tasks."
        "launch_headlesscode_session_task"
    ),
    max_retries=2,
    default_retry_delay=30,
)
def launch_headlesscode_session_task(
    self,
    project_id: int,
    chatbot_id: int | None,
    task_description: str,
    mode: str | None,
    tenant_key: str,
    account_id: int,
    idempotency_key: str,
    conversation_id: int | None = None,
    project_name: str = "",
) -> dict:
    """Start one headlesscode session and persist its session row.

    Parameters are passed explicitly (not via contextvars) because
    Celery tasks run in separate worker processes across a broker
    round-trip.  *account_id* feeds the completion-handler chain
    (Phase 4's usage debit); *tenant_key* scopes DB access to the
    user's schema; *idempotency_key* guards against double-launching
    on retry (see module docstring).
    """
    from airunner_services.data.tenant import tenant_scope

    with tenant_scope(tenant_key):
        repo_path = _load_project_workspace_root(project_id)
        if repo_path is None:
            logger.warning(
                "Headlesscode launch: project %d missing", project_id,
            )
            return {"status": "error", "reason": "project_missing"}

        session_id, resolved_mode = _start_session_or_retry(
            self, project_id, repo_path, task_description, mode,
            idempotency_key,
        )

        if not session_id:
            # Log the state transition, not the raw body — the
            # response may carry the repo's filesystem path.
            logger.error(
                "Headlesscode launch: start_session returned no "
                "sessionId for project %d",
                project_id,
            )
            return {"status": "error", "reason": "no_session_id"}

        _persist_session_row(
            project_id, chatbot_id, task_description, resolved_mode,
            session_id, conversation_id,
        )
        append_session_card_entry(
            conversation_id, session_id,
            HeadlesscodeSessionStatus.RUNNING.value,
            project_name, task_description, resolved_mode,
        )

    logger.info(
        "Headlesscode session started: hc=%s project=%d account=%d",
        session_id, project_id, account_id,
    )
    return {"status": "started", "session_id": session_id}


def finalize_session_usage(
    account_id: int, headlesscode_session_id: str, cost_usd: Decimal
) -> Decimal:
    """Completion handler — debit one finished session's real cost.

    Called by the session-lifecycle owner (Phase 4's polling loop)
    when a session reaches a terminal state.  Idempotent: the
    ledger's ``session_debit`` rows keyed by the real headlesscode
    session id prevent double-debiting on retries.
    """
    from projects.uwuchat.server.code_credits_service import (
        debit_session_usage,
    )

    return debit_session_usage(
        account_id, headlesscode_session_id, cost_usd,
    )


def _persist_session_row(
    project_id: int,
    chatbot_id: int | None,
    task_description: str,
    mode: str | None,
    session_id: str,
    conversation_id: int | None,
) -> None:
    """Insert the headlesscode_sessions row for a started session."""
    from airunner_services.database.session import session_scope

    from projects.uwuchat.server.models.headlesscode_session import (
        HeadlesscodeSession,
        HeadlesscodeSessionStatus,
    )

    with session_scope() as session:
        session.add(HeadlesscodeSession(
            project_id=project_id,
            chatbot_id=chatbot_id,
            conversation_id=conversation_id,
            headlesscode_session_id=session_id,
            status=HeadlesscodeSessionStatus.RUNNING.value,
            task_description=task_description,
            mode=mode,
        ))
        session.commit()


def _run_async(coro):
    """Run an async coroutine in a sync context (Celery task)."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
