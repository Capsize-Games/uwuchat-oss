"""Session management for the persistent UwU conversation thread.

Handles session-gap detection (4 h) and lazy episodic summarization.
A session is an invisible backend concept — users see one continuous thread
per UwU.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional, Tuple

from airunner_services.database.models.chat_session import (
    ChatSession,
    SESSION_GAP_HOURS,
)
from airunner_services.database.models.chatbot import Chatbot
from airunner_services.database.models.conversation import Conversation

logger = logging.getLogger(__name__)


class SessionManager:
    """Manage session lifecycle for one UwU (chatbot)."""

    def _fetch_last_session(self, chatbot_id: int) -> Optional[ChatSession]:
        """Return the most recent session for *chatbot_id*."""
        return (
            ChatSession.objects.query()
            .filter(ChatSession.chatbot_id == chatbot_id)
            .order_by(ChatSession.last_message_at.desc())
            .first()
        )

    def _detect_gap(
        self, last_session: Optional[ChatSession], now: datetime.datetime
    ) -> bool:
        """Return True if no session exists or the gap exceeds the threshold."""
        return last_session is None or (
            (now - last_session.last_message_at)
            > datetime.timedelta(hours=SESSION_GAP_HOURS)
        )

    def _start_fresh_session(
        self,
        chatbot_id: int,
        user_id: Optional[int],
        now: datetime.datetime,
    ) -> Tuple[ChatSession, Optional[Conversation]]:
        """Create a new session (gap exceeded or first ever).

        No Conversation is created here — that only happens when a
        message is actually sent (via handle_request).
        """
        session = ChatSession.objects.create(
            chatbot_id=chatbot_id,
            user_id=user_id,
            started_at=now,
            last_message_at=now,
            summary_ready=False,
        )
        return session, None

    def _resume_existing_session(
        self,
        last_session: ChatSession,
        chatbot_id: int,
        now: datetime.datetime,
    ) -> Tuple[ChatSession, Optional[Conversation]]:
        """Reuse the existing session, updating its last_message_at.

        No new Conversation is created here — that only happens when
        a message is actually sent (via handle_request).
        """
        ChatSession.objects.update(last_session.id, last_message_at=now)
        conv = Conversation.objects.filter_by_first(
            session_id=last_session.id, current=True
        ) or Conversation.objects.filter_by_first(session_id=last_session.id)
        return last_session, conv

    def get_or_create_session(
        self,
        chatbot_id: int,
        user_id: Optional[int] = None,
    ) -> Tuple[ChatSession, Optional[Conversation], Optional[int], float]:
        """Return the active session, rotating if gap exceeded.

        No Conversation is created here — that only happens when a
        message is sent (via handle_request).  Returns the most recent
        existing Conversation (or None) so callers can use it for
        message persistence.

        Returns:
            (session, conversation_or_none, cold_session_id, gap_hours)

        ``cold_session_id_to_summarize`` is non-None when the previous
        session went cold and needs a lazy background summary — the caller
        should fire ``asyncio.create_task(summarize_session(id))``.
        ``gap_hours`` is the elapsed hours since last activity (0 if resuming).
        """
        now = datetime.datetime.utcnow()
        cold_id: Optional[int] = None
        gap_hours: float = 0.0

        last_session = self._fetch_last_session(chatbot_id)
        gap_exceeded = self._detect_gap(last_session, now)

        if gap_exceeded:
            gap_seconds: float | None = None
            if last_session:
                if not last_session.summary_ready:
                    cold_id = last_session.id
                delta = now - last_session.last_message_at
                gap_hours = delta.total_seconds() / 3600
                gap_seconds = delta.total_seconds()
            session, conv = self._start_fresh_session(
                chatbot_id, user_id, now,
            )

            try:
                from airunner_services.events.recorder import record

                record(
                    "session_start",
                    chatbot_id=chatbot_id,
                    actor="system",
                    payload={
                        "session_id": session.id,
                        "gap_seconds": gap_seconds,
                    },
                    session_id=session.id,
                )
            except Exception:
                pass
        else:
            session, conv = self._resume_existing_session(
                last_session, chatbot_id, now
            )

        # Mark the chatbot as current so downstream code that resolves the
        # chatbot via get_chatbot() (e.g. prompt-builder identity parts)
        # picks up the correct name, personality, and settings instead of
        # a stale chatbot that was current from a previous selection.
        Chatbot.make_current(chatbot_id)

        if conv and conv.id:
            Conversation.make_current(conv.id)

        return session, conv, cold_id, gap_hours

    def pending_cold_sessions(self, chatbot_id: int) -> list[int]:
        """Return ids of past sessions still missing an episodic summary.

        Excludes the chatbot's current (most recent) session, which is
        still active and must never be summarized while in use.
        """
        last_session = self._fetch_last_session(chatbot_id)
        active_id = last_session.id if last_session else None
        rows = (
            ChatSession.objects.query()
            .filter(ChatSession.chatbot_id == chatbot_id)
            .filter(ChatSession.summary_ready.is_(False))
            .all()
        )
        return [s.id for s in rows if s.id != active_id]

    # Number of ``Conversation`` rows to fetch per DB query window.
    # Each row's ``value`` column is a ``UserEncryptedText`` that is
    # decrypted at ORM-hydration time, so bounding this directly
    # limits both the SQL row-count and the per-request CPU cost.
    _CONV_WINDOW = 20

    def load_thread(
        self,
        chatbot_id: int,
        limit: int = 200,
        offset: int = 0,
    ) -> Tuple[list, int]:
        """Return recent messages for a chatbot across sessions.

        Fetches ``Conversation`` rows in windowed batches (newest
        first) and stops once enough messages have been accumulated
        to satisfy ``limit + offset``.  ``ChatSession`` rows are
        batch-fetched to eliminate the N+1 query pattern.

        Returns the most recent ``limit`` messages (tail of the full
        history) so that new messages are never cut off when the total
        exceeds ``limit``.  Each message dict includes ``session_id``
        and ``session_started_at`` so the frontend can render
        session-gap dividers.
        """
        target = limit + offset
        flat: list[dict] = []
        session_ids: set[int] = set()
        db_offset = 0
        first_window = True

        # Index-only pre-count (no ``value`` decryption).  Combined
        # with the windowed fetch below it bounds the number of
        # windows, so rows whose messages pagination would discard
        # are never fetched at all.
        row_count = (
            Conversation.objects.query()
            .filter(Conversation.chatbot_id == chatbot_id)
            .count()
        )
        max_windows = (
            row_count + self._CONV_WINDOW - 1
        ) // self._CONV_WINDOW
        windows_fetched = 0

        while (
            len(flat) < target and windows_fetched < max_windows
        ):
            window = (
                Conversation.objects.query()
                .filter(Conversation.chatbot_id == chatbot_id)
                .order_by(Conversation.id.desc())
                .limit(self._CONV_WINDOW)
                .offset(db_offset)
                .all()
            )
            if not window:
                break

            # Clean up orphaned user messages from the most recent
            # conversation (first row in the first descending window).
            if first_window:
                first_window = False
                from airunner_services.conversations.conversation_history_manager import (
                    trim_orphaned_user_message,
                )
                trim_orphaned_user_message(window[0])

            # Each conversation's message list is ascending
            # (oldest→newest).  Since we are walking conversations
            # newest→oldest, we reverse within each conversation so
            # the flat list accumulates newest→oldest overall.
            for conv in window:
                msgs = getattr(conv, "value", None) or []
                if not isinstance(msgs, list):
                    logger.error(
                        "SessionManager.load_thread: conversation "
                        "%s (chatbot_id=%s) returned non-list "
                        "value (type=%s, len=%d). This indicates "
                        "a decryption failure — the "
                        "UserEncryptedText column could not be "
                        "decrypted. Skipping.",
                        getattr(conv, "id", "?"),
                        chatbot_id,
                        type(msgs).__name__,
                        len(msgs) if hasattr(msgs, "__len__")
                        else 0,
                    )
                    continue
                sid = getattr(conv, "session_id", None)
                if sid is not None:
                    session_ids.add(sid)

                for msg in reversed(msgs):
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("metadata_type") in (
                        "proactive_trigger",
                        "tool_calls",
                        "tool_result",
                    ):
                        continue
                    enriched = dict(msg)
                    enriched["session_id"] = sid
                    flat.append(enriched)
                    if len(flat) >= target:
                        break
                if len(flat) >= target:
                    break

            db_offset += self._CONV_WINDOW
            windows_fetched += 1

        # Batch-fetch all referenced ChatSession rows in one query.
        session_map: dict[int, ChatSession] = {}
        if session_ids:
            sessions = (
                ChatSession.objects.query()
                .filter(ChatSession.id.in_(list(session_ids)))
                .all()
            )
            session_map = {s.id: s for s in sessions}

        # Reverse so messages are ascending (oldest→newest), then
        # stamp session_started_at on each message.
        flat.reverse()
        for msg in flat:
            sid = msg.get("session_id")
            if sid is not None:
                sess = session_map.get(sid)
                if sess and sess.started_at:
                    msg["session_started_at"] = (
                        sess.started_at.isoformat()
                    )

        total = len(flat)
        if offset == 0:
            page = flat[max(0, total - limit):]
        else:
            page = flat[max(0, total - limit - offset):max(
                0, total - offset
            )]
        return page, total

    def persist_greeting(
        self, chatbot_id: int, greeting: str
    ) -> None:
        """Persist an opening greeting as the first Conversation row.

        Creates a ``Conversation`` row with ``current=False`` containing
        only the greeting message.  This is intentionally separate from
        the main conversation flow (which creates rows via
        ``Conversation.create()`` / ``make_current()``) so the greeting
        does not become the active current conversation.

        Idempotent: if *any* ``Conversation`` row already exists for this
        ``chatbot_id``, this is a no-op.  This guards against duplicate
        rows from network retries or double-invocation without needing a
        dedicated dedupe table.
        """
        existing = Conversation.objects.filter_by_first(
            chatbot_id=chatbot_id,
        )
        if existing:
            return

        session, _conv, _cold_id, _gap = self.get_or_create_session(
            chatbot_id,
        )
        chatbot = Chatbot.objects.get(chatbot_id)
        botname = getattr(chatbot, "botname", "") if chatbot else ""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        Conversation.objects.create(
            chatbot_id=chatbot_id,
            session_id=session.id,
            chatbot_name=botname,
            user_id=None,
            user_name="",
            value=[{
                "role": "assistant",
                "content": greeting,
                "timestamp": now,
            }],
            current=False,
        )


def touch_session_last_message_at(conversation_id: Optional[int]) -> None:
    """Update last_message_at for the ChatSession linked to conversation_id.

    Called after each generation so the gap detection always reflects the
    time of the last real message, not the last page-load.
    """
    if not conversation_id:
        return
    try:
        conv = Conversation.objects.get(conversation_id)
        if conv is None:
            return
        session_id = getattr(conv, "session_id", None)
        if not session_id:
            return
        ChatSession.objects.update(
            session_id,
            last_message_at=datetime.datetime.utcnow(),
        )
    except Exception as exc:
        logger.debug("touch_session_last_message_at failed: %s", exc)


