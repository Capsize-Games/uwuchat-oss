"""Per-session headlesscode event-polling helpers (Phase 4: relay).

Pure-ish helpers shared by the Celery poll task
(``tasks/headlesscode_poll_tasks.py``) and its unit tests: loading the
session/project context, persisting new feed events with their
``turn``/``system`` grouping, advancing the poll cursor, driving
session status transitions, and appending forwardable payloads to the
Redis outbox (``headlesscode_event_store``).

No Celery imports here, so plain unit tests can exercise the whole
poll cycle against fake sessions/Redis.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from projects.uwuchat.server.headlesscode_chat_grouping import (
    chat_block_kinds,
)


def load_session_context(
    session: Any, session_id: int,
) -> tuple[Any, Any]:
    """Return ``(row, project)``, or ``(None, reason)`` when the
    session is missing, deleted, inactive, or its project is gone.

    A *paused* session is still polled: the only way it can observe a
    later ``resumed`` event is by continuing to poll its feed.
    """
    from projects.uwuchat.server.models.headlesscode_project import (
        HeadlesscodeProject,
    )
    from projects.uwuchat.server.models.headlesscode_session import (
        HeadlesscodeSession,
        HeadlesscodeSessionStatus,
    )

    row = session.query(HeadlesscodeSession).get(session_id)
    if row is None or row.deleted:
        return None, "missing"
    active = (
        HeadlesscodeSessionStatus.RUNNING.value,
        HeadlesscodeSessionStatus.PAUSED.value,
    )
    if row.status not in active:
        return None, "not_running"
    project = session.query(HeadlesscodeProject).get(row.project_id)
    if project is None or project.deleted:
        return None, "project_missing"
    return row, project


def safe_next_offset(
    raw_next_offset: Any, current_offset: int, session_id: int,
) -> int:
    """Return the next poll cursor, never moving it backwards.

    The feed uses byte-offset cursors; a shrunken/recreated feed file
    reports a lower offset and would re-return old events. Hold the
    cursor where it is rather than re-reading history.
    """
    next_offset = int(raw_next_offset or current_offset)
    if next_offset < current_offset:
        return current_offset
    return next_offset


def persist_new_events(
    session: Any, row: Any, new_events: list[dict],
) -> list[str]:
    """Persist *new_events* rows with full-feed grouping; return kinds."""
    if not new_events:
        return []
    from projects.uwuchat.server.models.headlesscode_session_event import (
        HeadlesscodeSessionEvent,
    )

    stored = load_stored_feed(session, row.id)
    kinds = chat_block_kinds(stored + new_events)
    new_kinds = kinds[len(stored):]
    for event, kind in zip(new_events, new_kinds):
        session.add(HeadlesscodeSessionEvent(
            session_id=row.id,
            raw_event=event,
            chat_block_kind=kind,
        ))
    return new_kinds


def load_stored_feed(session: Any, session_id: int) -> list[dict]:
    """Return stored raw events for *session_id* in feed order."""
    from projects.uwuchat.server.models.headlesscode_session_event import (
        HeadlesscodeSessionEvent,
    )

    rows = (
        session.query(HeadlesscodeSessionEvent.raw_event)
        .filter(HeadlesscodeSessionEvent.session_id == session_id)
        .order_by(HeadlesscodeSessionEvent.id)
        .all()
    )
    return [dict(row[0]) for row in rows]


def apply_status_transitions(
    row: Any, events: list[dict],
) -> tuple[str | None, Decimal | None]:
    """Advance *row.status* from pause/resume/terminal events.

    Returns ``(new_status_or_None, terminal_cost_or_None)``. A
    ``session_end`` event carries the session's real ``costUsd``, which
    the caller settles with ``finalize_session_usage`` (idempotent per
    headlesscode session id).
    """
    from projects.uwuchat.server.models.headlesscode_session import (
        HeadlesscodeSessionStatus as S,
    )

    changed: str | None = None
    terminal_cost: Decimal | None = None
    for event in events:
        etype = event.get("type")
        if etype == "paused" and row.status == S.RUNNING.value:
            row.status = S.PAUSED.value
            changed = S.PAUSED.value
        elif etype == "resumed" and row.status == S.PAUSED.value:
            row.status = S.RUNNING.value
            changed = S.RUNNING.value
        elif etype == "session_end":
            terminal = (
                S.COMPLETED.value
                if event.get("status") == "success"
                else S.FAILED.value
            )
            if row.status not in (S.COMPLETED.value, S.FAILED.value):
                row.status = terminal
                changed = terminal
                cost = event.get("costUsd")
                if cost is not None:
                    terminal_cost = Decimal(str(cost))
    return changed, terminal_cost


def forward_new(
    account_id: int,
    snapshot: dict,
    new_events: list[dict],
    kinds: list[str],
    status_change: str | None,
) -> None:
    """Append one outbox payload per new event (plus status change)."""
    from projects.uwuchat.server.headlesscode_event_store import (
        headlesscode_events_append,
    )

    for event, kind in zip(new_events, kinds):
        headlesscode_events_append({
            "account_id": account_id,
            "session_id": snapshot["row_id"],
            "headlesscode_session_id": snapshot["hc_session_id"],
            "status": snapshot["status"],
            "chat_block_kind": kind,
            "event": event,
        })
    if status_change is not None:
        headlesscode_events_append({
            "account_id": account_id,
            "session_id": snapshot["row_id"],
            "headlesscode_session_id": snapshot["hc_session_id"],
            "status": snapshot["status"],
            "chat_block_kind": None,
            "event": None,
        })


__all__ = [
    "apply_status_transitions",
    "forward_new",
    "load_session_context",
    "load_stored_feed",
    "persist_new_events",
    "safe_next_offset",
]
