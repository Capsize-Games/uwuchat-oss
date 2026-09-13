"""Backfill conversations.session_id for orphaned historical rows.

Revision ID: f2b3c13e6a1a
Revises: f2b3c13e6a19
Create Date: 2026-07-08
"""

from datetime import datetime, timedelta
from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2b3c13e6a1a"
down_revision: Union[str, None] = "f2b3c13e6a19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MAX_MATCH_DISTANCE = timedelta(hours=24)


def upgrade() -> None:
    """Backfill session_id on orphaned Conversation rows."""
    conn = op.get_bind()
    matched, unmatched = _backfill_session_ids(conn)
    schema = _current_schema(conn)
    logger = _get_logger()
    logger.info(
        "[backfill-session-id] schema=%s matched=%s unmatched=%s",
        schema, matched, unmatched,
    )


def downgrade() -> None:
    """No-op: backfilling is not meaningfully reversible.

    The prior state was "unknown," not "NULL is correct."  There is
    no recoverable pre-backfill value to restore, so a reverse
    migration would be destructive without adding value.
    """


# ---------------------------------------------------------------------------
# Backfill logic
# ---------------------------------------------------------------------------


def _backfill_session_ids(conn) -> tuple[int, int]:
    """Backfill session_id for all orphaned conversations in the
    current schema.  Returns (matched, unmatched)."""
    conversations_t = sa.Table(
        "conversations", sa.MetaData(),
        autoload_with=conn,
    )
    sessions_t = sa.Table(
        "chat_sessions", sa.MetaData(),
        autoload_with=conn,
    )

    # Only work on rows that have no session_id yet — this is the
    # natural idempotency guard: once backfilled, a row drops out
    # of this result set on the next run.
    orphaned = conn.execute(
        sa.select(
            conversations_t.c.id,
            conversations_t.c.chatbot_id,
            conversations_t.c.updated_at,
        ).where(conversations_t.c.session_id.is_(None))
    ).fetchall()

    matched = 0
    unmatched = 0
    for conv_id, chatbot_id, updated_at in orphaned:
        if updated_at is None:
            unmatched += 1
            continue
        sessions = conn.execute(
            sa.select(
                sessions_t.c.id,
                sessions_t.c.started_at,
                sessions_t.c.last_message_at,
            ).where(sessions_t.c.chatbot_id == chatbot_id)
        ).fetchall()
        best_id = _best_session_match(updated_at, sessions)
        if best_id is None:
            unmatched += 1
            continue
        conn.execute(
            conversations_t.update()
            .where(conversations_t.c.id == conv_id)
            .values(session_id=best_id)
        )
        matched += 1
    return matched, unmatched


def _best_session_match(
    updated_at: datetime,
    sessions: list[tuple[int, datetime, datetime]],
) -> Optional[int]:
    """Return the best matching session id for a conversation, or None.

    Steps (in priority order):
    1. Session whose [started_at, last_message_at] window contains
       updated_at — strongest signal.
    2. Session whose last_message_at is closest to updated_at AND
       within _MAX_MATCH_DISTANCE — fallback.
    3. None — leave unmatched; a wrong link is worse than NULL.
    """
    if not sessions:
        return None
    # Ensure updated_at is offset-naive for comparison (sessions
    # columns are naive UTC — same storage convention as
    # ConversationTurn.created_at).
    if updated_at.tzinfo is not None:
        updated_at = updated_at.replace(tzinfo=None)

    # Step 1: exact window containment.
    for sid, started, last_msg in sessions:
        if started is None or last_msg is None:
            continue
        if started <= updated_at <= last_msg:
            return sid

    # Step 2: closest last_message_at within _MAX_MATCH_DISTANCE.
    best_sid: Optional[int] = None
    best_dist: Optional[timedelta] = None
    for sid, _started, last_msg in sessions:
        if last_msg is None:
            continue
        dist = abs(updated_at - last_msg)
        if dist > _MAX_MATCH_DISTANCE:
            continue
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_sid = sid
    return best_sid


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _current_schema(conn) -> str:
    """Return the current PostgreSQL schema name."""
    try:
        return conn.execute(sa.text("SELECT current_schema()")).scalar()
    except Exception:
        return "unknown"


def _get_logger():
    """Return a logger — migrations run before the app logger is
    configured, so fall back to a plain stdlib logger."""
    import logging
    return logging.getLogger("alembic")
