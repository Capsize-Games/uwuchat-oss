"""Save concern — extracts new personal facts worth remembering."""

from __future__ import annotations

import re
from typing import Any

from airunner_services.llm.managers.concerns.base_concern import BaseConcern

_SAVE_PROMPT = (
    "{context_block}"
    'Latest message: "{message}"\n\n'
    "Does this message contain a new personal detail about the user "
    "that is worth remembering?\n"
    "This includes: the name of someone in their life, a personal "
    "preference (food, music, hobbies, etc.), an event from their "
    "life they describe, a feeling they express about something "
    "personal, or a personal fact about their circumstances.\n"
    "Do NOT extract: opinions about external events, generic "
    "questions, complaints about things, or anything that is not "
    "a specific fact about the user themselves.\n"
    "If YES, extract the fact as one concise sentence.\n"
    "If NO, answer NO.\n\n"
    "Format exactly: 'YES: concise fact here' or 'NO'"
)

_YES_RE = re.compile(
    r"^\s*yes\s*[:\-]\s*(.+)", re.IGNORECASE | re.DOTALL
)

_FACT_MAX_LEN = 300


class SaveConcern(BaseConcern):
    """Fires when the user shares a new personal detail worth saving."""

    tool_name = "save_knowledge"

    def _build_prompt(self, user_message: str, context: str) -> str:
        """Build the save-or-not classification prompt."""
        context_block = (
            f"Conversation so far:\n{context}\n\n" if context else ""
        )
        return _SAVE_PROMPT.format(
            context_block=context_block,
            message=user_message[:400],
        )

    def _parse(self, text: str) -> tuple[bool, dict[str, Any]]:
        """Parse YES/NO response into save_knowledge args."""
        m = _YES_RE.match(text)
        if not m:
            return False, {}
        fact = m.group(1).strip()[: _FACT_MAX_LEN].strip()
        if not fact:
            return False, {}
        return True, {"fact": fact, "subject": "user"}
