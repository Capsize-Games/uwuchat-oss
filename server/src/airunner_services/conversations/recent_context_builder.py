"""Build a recent-conversation context block for LLM system-prompt injection.

Fetches the last N past conversations (excluding the current one, within a
rolling date window), generates an extractive summary for each, and formats
them into a compact markdown block that can be appended to the system prompt.

Summaries are cached in ``Conversation.summary`` and invalidated whenever the
message count changes (tracked via ``last_analyzed_message_id``).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

_DAYS_LOOKBACK = 30
_MAX_CONVERSATIONS = 10
_MAX_CONTEXT_CHARS = 2000
_LEXRANK_SENTENCES = 3
_LAST_EXCHANGE_CHARS = 120


class RecentConversationContextBuilder:
    """Build a recent-past-conversation context block using Python only."""

    def build_context(
        self,
        current_conversation_id: Optional[int],
        chatbot_id: Optional[int] = None,
    ) -> str:
        """Return a formatted markdown block of recent conversation summaries.

        Returns an empty string when there are no past conversations, when
        all summaries are empty, or when chatbot_id is None (scoping
        prevents cross-chatbot leaks).
        """
        if chatbot_id is None:
            return ""
        conversations = self._fetch_recent(
            chatbot_id, current_conversation_id
        )
        if not conversations:
            return ""

        blocks: list[str] = []
        for conv in conversations:
            block = self._conversation_block(conv)
            if block:
                blocks.append(block)

        if not blocks:
            return ""

        joined = "\n\n".join(blocks)
        return joined[:_MAX_CONTEXT_CHARS]

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_recent(
        chatbot_id: int,
        exclude_id: Optional[int],
    ):
        """Return up to _MAX_CONVERSATIONS conversations for *chatbot_id*
        within the date window, excluding *exclude_id*.
        """
        try:
            from airunner_services.database.models.conversation import (
                Conversation,
            )

            cutoff = datetime.now(UTC) - timedelta(days=_DAYS_LOOKBACK)
            query = (
                Conversation.objects.query()
                .filter(Conversation.chatbot_id == chatbot_id)
                .filter(Conversation.created_at >= cutoff)
                .order_by(Conversation.id.desc())
            )
            if exclude_id is not None:
                query = query.filter(Conversation.id != exclude_id)
            return query.limit(_MAX_CONVERSATIONS).all()
        except Exception as exc:
            logger.debug("[RECENT CTX] Fetch failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Block assembly
    # ------------------------------------------------------------------

    def _conversation_block(self, conv) -> str:
        """Return a single formatted block for one conversation."""
        messages: list = getattr(conv, "value", None) or []
        if not messages:
            return ""

        lexrank_summary = self._get_or_build_summary(conv, messages)
        last_exchange = self._last_exchange(messages)

        parts: list[str] = []
        if lexrank_summary:
            parts.append(lexrank_summary)
        if last_exchange:
            parts.append(f"Last exchange: {last_exchange}")

        if not parts:
            return ""

        date_str = ""
        created = getattr(conv, "created_at", None)
        if created:
            try:
                date_str = created.date().isoformat()
            except Exception:
                pass
        header = date_str or f"conversation {getattr(conv, 'id', '?')}"

        return f"[{header}]\n" + "\n".join(parts)

    # ------------------------------------------------------------------
    # Summary (LexRank, cached)
    # ------------------------------------------------------------------

    def _get_or_build_summary(self, conv, messages: list) -> str:
        """Return a cached LexRank summary, regenerating when stale."""
        msg_count = len(messages)
        cached_summary = str(getattr(conv, "summary", "") or "").strip()
        cached_count = getattr(conv, "last_analyzed_message_id", None) or 0

        if cached_summary and cached_count == msg_count:
            return cached_summary

        summary = self._lexrank_summary(conv, messages)
        if summary:
            self._persist_summary(conv, summary, msg_count)
        return summary

    @staticmethod
    def _lexrank_summary(conv, messages: list) -> str:
        """Generate a LexRank extractive summary from conversation messages."""
        full_text = ""
        try:
            full_text = conv.formatted_messages
        except Exception:
            pass
        if not full_text or not full_text.strip():
            return ""
        try:
            from sumy.nlp.tokenizers import Tokenizer
            from sumy.parsers.plaintext import PlaintextParser
            from sumy.summarizers.lex_rank import LexRankSummarizer

            parser = PlaintextParser.from_string(
                full_text, Tokenizer("english")
            )
            summarizer = LexRankSummarizer()
            sentences = summarizer(parser.document, _LEXRANK_SENTENCES)
            return " ".join(str(s) for s in sentences).strip()
        except Exception as exc:
            logger.debug(
                "[RECENT CTX] LexRank failed for conv %s: %s",
                getattr(conv, "id", "?"),
                exc,
            )
            return ""

    @staticmethod
    def _persist_summary(conv, summary: str, msg_count: int) -> None:
        """Cache the summary and message count on the conversation row."""
        try:
            from airunner_services.database.models.conversation import (
                Conversation,
            )

            conv_id = getattr(conv, "id", None)
            if conv_id:
                Conversation.objects.update(
                    conv_id,
                    summary=summary,
                    last_analyzed_message_id=msg_count,
                )
        except Exception as exc:
            logger.debug("[RECENT CTX] Persist summary failed: %s", exc)

    # ------------------------------------------------------------------
    # Last exchange
    # ------------------------------------------------------------------

    @staticmethod
    def _last_exchange(messages: list) -> str:
        """Return a compact 'user → bot' snippet of the final exchange."""
        last_human = next(
            (m for m in reversed(messages) if not m.get("is_bot")), None
        )
        last_bot = next(
            (m for m in reversed(messages) if m.get("is_bot")), None
        )
        if not last_human or not last_bot:
            return ""
        human_text = str(last_human.get("content", "") or "")[
            :_LAST_EXCHANGE_CHARS
        ].strip()
        bot_text = str(last_bot.get("content", "") or "")[
            :_LAST_EXCHANGE_CHARS
        ].strip()
        if not human_text or not bot_text:
            return ""
        return f'"{human_text}" → "{bot_text}"'
