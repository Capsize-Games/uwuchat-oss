"""Search concern — decides whether to fire a web search tool."""

from __future__ import annotations

import re
from typing import Any

from airunner_services.llm.managers.concerns.base_concern import BaseConcern

# IMPORTANT: Keep all prompts generic. Never embed real-world names,
# events, people, or topics from active test conversations here.
_SEARCH_CLASSIFY_PROMPT = (
    "{context_block}"
    'Latest message: "{message}"\n\n'
    "Should a web search happen before responding to the latest message?\n"
    "Answer YES with a targeted search query if the message references\n"
    "any specific real-world fact, event, person, place, city, region,\n"
    "TV show, movie, song, album, music artist, band, music collective,\n"
    "label, music scene, news story, or cultural reference.\n"
    "IMPORTANT: Also answer YES when the user is sharing or confirming\n"
    "facts about real-world topics (artists, releases, collectives) —\n"
    "the assistant should look up those topics to contribute real\n"
    "information, not just echo back what the user said.\n"
    "The query MUST incorporate key entities already established in the\n"
    "conversation (names, subjects, people already discussed) — not just\n"
    "words from the latest message in isolation.\n"
    "Answer NO only for pure small talk, greetings, personal feelings,\n"
    "or questions solely about the user's own life with no external\n"
    "factual references. When in doubt, answer YES.\n\n"
    "Format exactly: 'YES: search query here' or 'NO'"
)

_YES_RE = re.compile(
    r"^\s*yes\s*[:\-]\s*(.+)", re.IGNORECASE | re.DOTALL
)

_SEARCH_TOOL_PRIORITY: tuple[str, ...] = (
    "get_topic_brief",
    "search_fastsearch",
    "search_fastsearch_news",
    "search_news",
)


class SearchConcern(BaseConcern):
    """Fires when the message references a fact needing current information."""

    tool_name = "get_topic_brief"

    def __init__(self, bound_tool_names: frozenset[str]) -> None:
        """Store available tool names for priority selection."""
        self._bound = bound_tool_names

    def _build_prompt(self, user_message: str, context: str) -> str:
        """Build the search-or-not classification prompt."""
        context_block = (
            f"Conversation so far:\n{context}\n\n" if context else ""
        )
        return _SEARCH_CLASSIFY_PROMPT.format(
            context_block=context_block,
            message=user_message[:400],
        )

    def _parse(self, text: str) -> tuple[bool, dict[str, Any]]:
        """Parse YES/NO response; return tool name + query args.

        For news tools, ``max_age_hours`` is included so the downstream
        tool can express freshness as a structured parameter instead of
        polluting the free-text query with literal dates.
        """
        m = _YES_RE.match(text)
        if not m:
            return False, {}
        query = m.group(1).strip().split("\n")[0].strip()
        if not query:
            return False, {}
        tool_name = self._resolve_tool_name()
        if tool_name == "search_fastsearch_news":
            return True, {
                "query": query,
                "__tool_name": tool_name,
                "max_age_hours": 24,
            }
        return True, {"query": query, "__tool_name": tool_name}

    def _resolve_tool_name(self) -> str:
        """Pick the best available search tool by priority."""
        for preferred in _SEARCH_TOOL_PRIORITY:
            if preferred in self._bound:
                return preferred
        return "search_news"
