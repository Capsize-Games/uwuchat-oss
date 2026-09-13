"""Upcoming events block for the agent memory prompt section.

Generates a deterministic list of upcoming/in-progress events from
``KnowledgeFact`` rows by **live-recomputing** ``temporal_status``
via ``compute_temporal_status`` — never trusting the stored column
alone.  All ORM attribute access happens inside the session; values
are extracted into plain strings before the session closes.
"""
from __future__ import annotations

import datetime


def upcoming_events_block(chatbot_id: int) -> str:
    """Return a block of upcoming/in-progress events for a chatbot.

    Queries candidate rows broadly (``event_date IS NOT NULL``,
    ``temporal_status != 'durable'``), live-recomputes
    ``temporal_status`` for each via ``compute_temporal_status``,
    and only includes rows that are ``upcoming`` or ``in_progress``
    as of today.  Opportunistically updates the stored column when
    it disagrees with the live computation.

    All attribute access happens inside ``session_scope()`` — plain
    values are extracted before the session closes to avoid
    ``DetachedInstanceError``.
    """
    try:
        from airunner_services.database.models.knowledge_fact import (
            KnowledgeFact,
        )
        from airunner_services.database.session import session_scope
        from airunner_services.fact_lifecycle import (
            compute_temporal_status,
        )

        today = datetime.date.today()
        lines: list[str] = []

        with session_scope() as session:
            candidates = (
                session.query(KnowledgeFact)
                .filter(
                    KnowledgeFact.chatbot_id == chatbot_id,
                    KnowledgeFact.event_date.isnot(None),
                    KnowledgeFact.temporal_status != "durable",
                    KnowledgeFact.deleted.is_(False),
                )
                .order_by(KnowledgeFact.event_date.asc())
                .limit(16)
                .all()
            )

            for fact in candidates:
                live_status = compute_temporal_status(
                    event_date=fact.event_date,
                    event_end_date=fact.event_end_date,
                    recurring=bool(fact.recurring),
                    reference_date=today,
                )

                # Opportunistic correction: update the stored column
                # when it disagrees with the live computation.
                if live_status != fact.temporal_status:
                    fact.temporal_status = live_status
                    fact.updated_at = datetime.datetime.now(
                        datetime.UTC
                    )

                if live_status not in ("upcoming", "in_progress"):
                    continue

                # Extract values NOW while the session is still open.
                line = _render_event_line(
                    str(fact.fact_text or "").strip(),
                    fact.event_date,
                    fact.event_end_date,
                )
                if line:
                    lines.append(line)

            if lines:
                session.flush()

        if not lines:
            return ""

        return "Known upcoming/current events:\n" + "\n".join(lines)
    except Exception:
        return ""


def _render_event_line(
    text: str,
    event_date,
    event_end_date,
) -> str:
    """Render one event as a bullet line from already-extracted values."""
    if not text:
        return ""
    if event_date:
        if event_end_date:
            return (
                f"- {text} ({event_date.isoformat()} to "
                f"{event_end_date.isoformat()})"
            )
        return f"- {text} ({event_date.isoformat()})"
    return f"- {text}"
