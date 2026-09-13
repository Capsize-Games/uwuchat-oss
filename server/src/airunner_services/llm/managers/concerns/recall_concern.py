"""Recall concern — checks if the bot should query personal memory."""

from __future__ import annotations

import re
from typing import Any

from airunner_services.llm.managers.concerns.base_concern import BaseConcern

_RECALL_PROMPT = (
    "{context_block}"
    'Latest message: "{message}"\n\n'
    "Does this message suggest the user expects you to remember "
    "something personal about them or about your shared history?\n"
    "This includes: their preferences, past events they have described, "
    "people they have mentioned, inside references, or anything they "
    "seem to assume you already know.\n"
    "If YES, provide a short query that captures what to recall.\n"
    "If NO (the message is generic, impersonal, or about external "
    "facts), just answer NO.\n\n"
    "Format exactly: 'YES: short recall query here' or 'NO'"
)

_YES_RE = re.compile(
    r"^\s*yes\s*[:\-]\s*(.+)", re.IGNORECASE | re.DOTALL
)


class RecallConcern(BaseConcern):
    """Fires when the user seems to expect the bot to remember something."""

    tool_name = "recall_knowledge"

    def _build_prompt(self, user_message: str, context: str) -> str:
        """Build the recall classification prompt."""
        context_block = (
            f"Conversation so far:\n{context}\n\n" if context else ""
        )
        return _RECALL_PROMPT.format(
            context_block=context_block,
            message=user_message[:400],
        )

    def _parse(self, text: str) -> tuple[bool, dict[str, Any]]:
        """Parse YES/NO response into recall_knowledge args."""
        m = _YES_RE.match(text)
        if not m:
            return False, {}
        query = m.group(1).strip().split("\n")[0].strip()
        if not query:
            return False, {}
        return True, {"query": query}
