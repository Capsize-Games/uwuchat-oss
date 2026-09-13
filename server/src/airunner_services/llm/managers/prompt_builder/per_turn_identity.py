"""Per-turn user identity context: name, pronouns.

Each _<field>_line() function is a pure renderer: user row in, one prompt
line (or None) out. user_identity_part() composes all of them into a
single block. Add new identity fields here as another _<field>_line()
plus one line in the composition list — do not create a new module.
"""

from __future__ import annotations

from typing import Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.prompt_builder import (
    CONVERSATIONAL_ACTIONS,
)


def user_identity_part(owner, action: LLMActionType) -> Optional[str]:
    """Return the '[Who you're talking to]' block for owner.user."""
    if action not in CONVERSATIONAL_ACTIONS:
        return None
    user = getattr(owner, "user", None)
    if not user:
        return None
    lines = [
        line
        for line in (
            _name_line(user),
            _gender_line(user),
        )
        if line
    ]
    if not lines:
        return None
    return "\n".join(["[Who you're talking to]", *lines])


def _name_line(user) -> Optional[str]:
    name = getattr(user, "display_name", None)
    return f"Their name: {name}" if name else None


def _gender_line(user) -> Optional[str]:
    gender = getattr(user, "gender", None)
    if not gender:
        return None
    return (
        f"Their gender: {gender} — use accurate pronouns and"
        " references for them; don't make an issue of it."
    )
