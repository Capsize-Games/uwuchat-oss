"""Phase 3 Feelings Engine — voice lock, specificity, inner state."""

from __future__ import annotations

from typing import Optional

_VOICE_LOCK_HEADER = (
    "STYLE ANCHORS — these are examples of how this character"
    " actually writes.\n"
    "Your output must be consistent with this voice."
    " Not inspired by it. Consistent with it."
)

_SPECIFICITY_INSTRUCTION = (
    "Ground your reply in something specific and concrete."
    " Draw only from what your character genuinely knows from their"
    " own established history and inner life."
    " Never invent stressors, events, or facts about the user"
    " to fill a response — if you don't know, leave it out."
    " CRITICAL: Never explain your own emotional state by referencing"
    " the user's circumstances. Your feelings come from inside you,"
    " not from what is happening to them."
)


def voice_lock_part(owner) -> Optional[str]:
    """Return STYLE ANCHORS block for this chatbot, or None."""
    chatbot = getattr(owner, "chatbot", None)
    if not chatbot:
        return None
    core = getattr(chatbot, "identity_core", None) or {}
    anchors = core.get("voice", {}).get("style_anchors", [])
    if not anchors:
        return None
    anchor_lines = "\n".join(f"[{a}]" for a in anchors[:6])
    return f"{_VOICE_LOCK_HEADER}\n\n{anchor_lines}"


def specificity_forcing_part() -> str:
    """Return the specificity forcing instruction."""
    return _SPECIFICITY_INSTRUCTION


def relationship_part(owner) -> Optional[str]:
    """Return relationship context for the current user, or None."""
    chatbot = getattr(owner, "chatbot", None)
    if not chatbot or not getattr(chatbot, "id", None):
        return None
    try:
        from airunner_services.database.models.user import User
        from airunner_services.world.relationship_engine import (
            get_relationship_context,
        )
        user = User.objects.query().first()
        if user is None:
            return None
        ctx = get_relationship_context(chatbot.id, "user", user.id)
        return ctx
    except Exception:
        return None


def belief_part(owner) -> Optional[str]:
    """Return BELIEF ANCHORS block from identity_core, or None."""
    chatbot = getattr(owner, "chatbot", None)
    if not chatbot:
        return None
    core = getattr(chatbot, "identity_core", None) or {}
    beliefs = core.get("beliefs", {})
    if not beliefs:
        return None
    lines = [
        "BELIEF ANCHORS (identity core — these positions are fixed"
        " and do not shift to match the user's views):"
    ]
    cultural = beliefs.get("cultural_values", [])
    if cultural:
        lines.append(f"Cultural values: {', '.join(cultural[:3])}")
    for topic, pos in list((beliefs.get("positions") or {}).items())[:3]:
        lines.append(f"{topic}: {pos}")
    sensitivities = beliefs.get("sensitivities", [])
    if sensitivities:
        lines.append(f"Uncomfortable with: {', '.join(sensitivities[:2])}")
    return "\n".join(lines) if len(lines) > 1 else None


def inner_state_constraint_part(owner) -> Optional[str]:
    """Return the inner state hard constraint block, or None."""
    chatbot = getattr(owner, "chatbot", None)
    if not chatbot:
        return None
    state = getattr(chatbot, "inner_state", None)
    if not state:
        return None
    preoccupations = state.get("preoccupations", [])
    if isinstance(preoccupations, list):
        preoccupations_str = ", ".join(str(p) for p in preoccupations)
    else:
        preoccupations_str = str(preoccupations)
    lines = [
        "YOUR CURRENT STATE"
        " (binding — your response must be consistent with this):",
        f"Situation: {state.get('situation', '')}",
        f"Emotional weather: {state.get('emotional_weather', '')}",
        f"Body: {state.get('body', '')}",
        f"Preoccupations: {preoccupations_str}",
        f"Needs: {state.get('needs', '')}",
        f"Current activity: {state.get('current_activity', '')}",
    ]
    return "\n".join(lines)
