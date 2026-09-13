"""Curiosity Engine — tracks topic interest and triggers FastSearch."""

from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

CURIOSITY_SEARCH_THRESHOLD: int = 3
SEARCH_COOLDOWN_HOURS: float = 12.0


def _curiosity_data(chatbot: Any) -> dict:
    """Return the curiosity_data dict, initializing if missing."""
    return dict(getattr(chatbot, "curiosity_data", None) or {})


def _topic_score(curiosity: dict, topic: str) -> int:
    """Return the curiosity score for one topic."""
    return int((curiosity.get("topics") or {}).get(topic, {}).get("score", 0))


def _hours_since_searched(curiosity: dict, topic: str) -> float:
    """Return hours since the topic was last searched (inf if never)."""
    entry = (curiosity.get("topics") or {}).get(topic, {})
    ts_str = entry.get("last_searched_at")
    if not ts_str:
        return float("inf")
    try:
        ts = datetime.datetime.fromisoformat(ts_str)
        return (datetime.datetime.utcnow() - ts).total_seconds() / 3600
    except Exception:
        return float("inf")


def _record_search(curiosity: dict, topic: str) -> dict:
    """Mark a topic as just-searched and return updated curiosity dict."""
    topics = dict(curiosity.get("topics") or {})
    entry = dict(topics.get(topic, {}))
    entry["last_searched_at"] = datetime.datetime.utcnow().isoformat()
    topics[topic] = entry
    curiosity = dict(curiosity)
    curiosity["topics"] = topics
    return curiosity


def bump_topics(
    chatbot_id: int,
    new_topics: list[str],
    current_curiosity: dict,
) -> dict:
    """Increment scores for topics recently encountered. Return updated dict."""
    topics = dict(current_curiosity.get("topics") or {})
    for topic in new_topics:
        entry = dict(topics.get(topic, {"score": 0}))
        entry["score"] = int(entry.get("score", 0)) + 1
        topics[topic] = entry
    updated = dict(current_curiosity)
    updated["topics"] = topics
    return updated


def _persist_curiosity(chatbot_id: int, data: dict) -> None:
    """Save curiosity_data back to the chatbot record."""
    try:
        from airunner_services.database.models.chatbot import Chatbot
        Chatbot.objects.update(chatbot_id, curiosity_data=data)
    except Exception:
        logger.exception(
            "Failed to persist curiosity_data for chatbot %s", chatbot_id
        )


class CuriosityEngine:
    """Evaluates chatbot curiosity and optionally triggers web searches."""

    def tick(self, chatbot: Any) -> Optional[list[str]]:
        """Return search result snippets if curiosity triggers a search."""
        curiosity = _curiosity_data(chatbot)
        preoccupations: list[str] = list(
            (chatbot.inner_state or {}).get("preoccupations") or []
        )
        if not preoccupations:
            return None

        curiosity = bump_topics(chatbot.id, preoccupations, curiosity)
        snippets: list[str] = []

        for topic in preoccupations:
            score = _topic_score(curiosity, topic)
            hours = _hours_since_searched(curiosity, topic)
            if score >= CURIOSITY_SEARCH_THRESHOLD and hours > SEARCH_COOLDOWN_HOURS:
                results = self._search(topic)
                if results:
                    snippets.extend(
                        r.get("title", r.get("body", ""))[:120]
                        for r in results[:2]
                    )
                    curiosity = _record_search(curiosity, topic)

        _persist_curiosity(chatbot.id, curiosity)
        return snippets or None

    def _search(self, topic: str) -> list[dict]:
        """Run a FastSearch for one topic."""
        try:
            from extensions.fastsearch.server.provider import (
                FastSearchProvider,
            )
            return FastSearchProvider().search(topic)
        except Exception:
            logger.exception("CuriosityEngine search failed for %r", topic)
            return []
