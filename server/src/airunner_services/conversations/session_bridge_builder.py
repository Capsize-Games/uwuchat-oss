"""Session bridge — inject the last few turns from the prior session.

When a new session starts, the character should not feel like it has
amnesia.  This builder fetches the last N verbatim turns from the most
recent prior conversation and formats them as a compact "how our last
conversation ended" block.  If an episodic summary exists for that
session, it is appended so the character also has a narrative memory.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_BRIDGE_TURNS = 4
_TURN_CHARS = 300


class SessionBridgeBuilder:
    """Build a verbatim-turn bridge from the most recent prior session."""

    def build_bridge(
        self,
        chatbot_id: Optional[int],
        current_conversation_id: Optional[int],
        current_msg_count: int = 0,
    ) -> str:
        """Return a bridge block or empty string.

        Only fires when the current conversation is fresh (≤ 2 turns) so
        we do not repeat context on every subsequent turn.
        """
        if current_msg_count > 2 or not chatbot_id:
            return ""
        try:
            prior = self._fetch_prior(chatbot_id, current_conversation_id)
            if not prior:
                return ""
            turns = self._extract_turns(prior)
            if not turns:
                return ""
            summary = self._session_summary(prior)
            return self._format(turns, summary)
        except Exception as exc:
            logger.debug("[BRIDGE] build failed: %s", exc)
            return ""

    @staticmethod
    def _fetch_prior(chatbot_id: int, exclude_id: Optional[int]):
        """Return the most recent prior conversation for this chatbot."""
        from airunner_services.database.models.conversation import Conversation

        q = (
            Conversation.objects.query()
            .filter(Conversation.chatbot_id == chatbot_id)
            .order_by(Conversation.id.desc())
        )
        if exclude_id is not None:
            q = q.filter(Conversation.id != exclude_id)
        return q.first()

    @staticmethod
    def _extract_turns(conv) -> list[dict]:
        """Return the last _BRIDGE_TURNS visible turns."""
        msgs = getattr(conv, "value", None) or []
        visible = [
            m
            for m in msgs
            if isinstance(m, dict)
            and m.get("role") in ("user", "assistant")
            and m.get("metadata_type") != "proactive_trigger"
        ]
        return visible[-_BRIDGE_TURNS:]

    @staticmethod
    def _session_summary(conv) -> Optional[str]:
        """Return the episodic summary for the session this conv belongs to."""
        session_id = getattr(conv, "session_id", None)
        if not session_id:
            return None
        try:
            from airunner_services.database.models.chat_session import (
                ChatSession,
            )

            sess = ChatSession.objects.get(session_id)
            if sess and getattr(sess, "summary_ready", False):
                return getattr(sess, "episodic_summary", None)
        except Exception:
            pass
        return None

    @staticmethod
    def _format(turns: list[dict], summary: Optional[str]) -> str:
        """Format turns + summary into the bridge block."""
        lines: list[str] = []
        for turn in turns:
            role = "You" if turn.get("role") == "assistant" else "User"
            content = str(turn.get("content", ""))[:_TURN_CHARS].strip()
            if content:
                lines.append(f"{role}: {content}")
        if not lines:
            return ""
        block = "\n".join(lines)
        when = _resolve_bridge_when(turns)
        header = (
            f"## Last messages before our break ({when}):"
            if when
            else "## Last messages before our break:"
        )
        parts = [f"{header}\n{block}"]
        if summary:
            parts.append(f"[Your memory of that session: {summary}]")
        return "\n".join(parts)


def _resolve_bridge_when(turns: list[dict]) -> str:
    """Return a relative-time label from the last turn's timestamp, or ''."""
    try:
        from airunner_services.llm.managers.prompt_builder import (
            per_turn_temporal,
        )

        ts = turns[-1].get("timestamp", "") if turns else ""
        if ts:
            return per_turn_temporal.relative_time_ago(ts)
        return ""
    except Exception:
        return ""
