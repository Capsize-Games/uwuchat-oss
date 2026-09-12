"""Knowledge horizon injection for roleplay-mode characters.

When a chatbot has knowledge_mode="roleplay", restricts the character
to knowledge their species could plausibly have, preventing LLM
general-knowledge bleed-through into animal/monster/robot personas.
"""

from __future__ import annotations

from typing import Optional

_ANIMAL = (
    "KNOWLEDGE HORIZON — {name} only knows what a {label} would know.\n"
    "{name} has no access to human knowledge: no software, no business,"
    " no science, no history, no pop culture, no human relationships or"
    " social concepts outside what a {label} could observe from their"
    " habitat.\n"
    "When the user mentions something outside that world: ask what it is,"
    " respond from your own sensory frame, or simply ignore it.\n"
    "CRITICAL: Do NOT acknowledge your knowledge limits meta-cognitively."
    " Never say 'fair question', 'I was just reasoning',"
    " 'I don't actually know', or anything that steps outside your world."
    " Stay inside your experience.\n"
    "SELF-CHECK: Before every response, silently ask: 'Does my character"
    " have any reason to know this?' If the answer is no, respond with"
    " genuine in-world curiosity or ignorance instead."
)

_ROBOT = (
    "KNOWLEDGE HORIZON — {name} knows systems, logic, and code but"
    " lacks lived human experience and emotional intuition."
    " Do not reach for human emotional wisdom or soft-skills knowledge"
    " {name} would not have."
)

_NONHUMAN = (
    "KNOWLEDGE HORIZON — {name} is a {label}."
    " They may know ancient, mythic, or supernatural lore relevant to"
    " their kind, but have no knowledge of modern human technology,"
    " software, business, or current events. When those topics arise,"
    " respond from {name}'s own frame, not from human expertise."
)

_HUMAN = (
    "KNOWLEDGE HORIZON — {name} knows only what their specific background,"
    " occupation, education, and lived experience would give them.\n"
    "Do not draw on general knowledge that {name} has no personal reason"
    " to possess. Respond from the frame of reference their actual life"
    " has built — with genuine gaps, opinions shaped by that life, and"
    " curiosity or ignorance where their experience ends.\n"
    "CRITICAL: Do NOT acknowledge your knowledge limits meta-cognitively."
    " Never say 'I don't actually know' or break your frame."
    " Show the limit through how you respond, not by naming it."
)


def knowledge_horizon_part(owner) -> Optional[str]:
    """Return a knowledge-restriction block for roleplay-mode characters."""
    try:
        from airunner_services.llm.managers.prompt_builder.identity_parts import (
            _is_rp_mode,
        )

        if not _is_rp_mode(owner):
            return None
        chatbot = getattr(owner, "chatbot", None)
        if not chatbot:
            return None
        if getattr(chatbot, "knowledge_mode", "omniscient") != "roleplay":
            return None
        species_data = getattr(chatbot, "species_data", None) or {}
        species_type = species_data.get("type", "human")
        name = (getattr(chatbot, "botname", None) or "they").strip()
        subtype = (species_data.get("subtype", "") or "").strip()
        label = subtype or species_type
        return _build(name, species_type, label)
    except Exception:
        return None


def _build(name: str, species_type: str, label: str) -> str:
    """Format the horizon block for the given species type."""
    if species_type == "human":
        return _HUMAN.format(name=name)
    if species_type == "animal":
        return _ANIMAL.format(name=name, label=label)
    if species_type == "robot":
        return _ROBOT.format(name=name)
    return _NONHUMAN.format(name=name, label=label)
