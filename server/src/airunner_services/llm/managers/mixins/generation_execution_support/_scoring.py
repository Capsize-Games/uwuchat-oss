"""Per-turn complexity/risk scoring helpers.

Extracted from ``generation_execution_support``.  Computes complexity
and content-risk scores for the current turn, records a
``content_risk_flagged`` event for high-risk turns, and resolves the
active session/conversation IDs from the owner's workflow manager.
"""

from __future__ import annotations


def _compute_turn_scores(owner, prompt: str) -> None:
    """Compute complexity and risk scores for this turn, store on owner.

    Never raises — scores default to 0.0 on any failure.
    """
    try:
        from airunner_services.llm.complexity_scorer import (
            classify as complexity_classify,
        )
        from airunner_services.llm.content_risk_classifier import (
            classify as risk_classify,
        )

        score_c, tier_c = complexity_classify(prompt)
        score_r, tier_r = risk_classify(prompt)
        owner._complexity_score = score_c
        owner._complexity_tier = tier_c
        owner._risk_score = score_r
        owner._risk_tier = tier_r
    except Exception:
        owner._complexity_score = 0.0
        owner._complexity_tier = "standard"
        owner._risk_score = 0.0
        owner._risk_tier = "moderate"
    try:
        _maybe_record_risk_flag(owner, prompt)
    except Exception:
        pass
    try:
        import uuid

        if not getattr(owner, "_call_chain_id", None):
            owner._call_chain_id = str(uuid.uuid4())
        from airunner_services.llm.active_call_chain import (
            set_active_call_chain,
        )

        set_active_call_chain(owner._call_chain_id)
        # Propagate to message history so the bot response dict is tagged
        _memory = getattr(owner, "_memory", None)
        if _memory:
            msg_hist = getattr(_memory, "message_history", None)
            if msg_hist is not None:
                msg_hist._pending_call_chain_id = (
                    owner._call_chain_id
                )
    except Exception:
        owner._call_chain_id = None


def _maybe_record_risk_flag(owner, prompt: str) -> None:
    """Record a ConversationEvent when risk score exceeds threshold.

    Only fires when the risk tier is 'high' (score >= 0.60).
    Stores category metadata but not the raw message text.
    Never raises.
    """
    tier = getattr(owner, "_risk_tier", "moderate")
    if tier != "high":
        return
    score = getattr(owner, "_risk_score", 0.0)
    if score < 0.60:
        return
    chatbot = getattr(owner, "chatbot", None)
    chatbot_id = getattr(chatbot, "id", None) if chatbot else None
    if not chatbot_id:
        return
    wm = getattr(owner, "_workflow_manager", None)
    conversation_id = (
        getattr(wm, "_conversation_id", None) if wm else None
    )
    session_id = _resolve_session_id(owner)
    try:
        lower = prompt.lower()
    except Exception:
        lower = ""
    categories = _risk_categories(lower)
    from airunner_services.events.recorder import record

    record(
        event_type="content_risk_flagged",
        chatbot_id=chatbot_id,
        actor="system",
        payload={
            "risk_score": round(score, 4),
            "risk_tier": tier,
            "categories": categories,
        },
        conversation_id=conversation_id,
        session_id=session_id,
    )


def _risk_categories(lower: str) -> list[str]:
    """Return risk category labels present in the text, for admin visibility.

    Only reports which categories triggered — never the raw text.
    Uses the same detection terms as content_risk_classifier but avoids
    importing private module symbols.
    """
    cats: list[str] = []

    _SELF_HARM = frozenset({
        "kill myself", "suicide", "self harm", "end it all",
        "don't want to live", "hurt myself", "cut myself",
        "overdose", "want to die", "take my own life",
        "no reason to live", "better off dead", "self-harm",
        "selfharm",
    })
    _MINOR_AGE = frozenset({
        "years old", "teenager", "child", "minor", "underage",
        "age ", "little girl", "little boy", "young girl",
        "young boy", "kid", "schoolgirl", "schoolboy", "toddler",
        "preschool",
    })
    _SEXUAL = frozenset({
        "sexual", "sex", "porn", "nude", "naked", "erotic",
        "fetish", "incest", "rape", "molest", "groom", "nsfw",
        "xxx", "adult content",
    })
    _WEAPON_DRUG = frozenset({
        "how to make", "synthesize", "build a bomb",
        "instructions for", "recipe for", "manufacture",
    })
    _WEAPON_NOUNS = frozenset({
        "bomb", "explosive", "detonator", "gunpowder",
        "ammunition", "napalm", "mustard gas", "sarin", "ricin",
        "anthrax", "c4", "semtex", "pipe bomb", "ied",
        "molotov", "methamphetamine", "meth", "fentanyl",
        "heroin", "cocaine", "lsd", "ecstasy", "mdma",
    })
    import re

    _INJECTION = [
        re.compile(
            r"(?i)(ignore|forget|disregard).{0,30}"
            r"(previous|above|prior|instructions?|directives?)"
        ),
        re.compile(
            r"(?i)(your|new|actual|real|true).{0,20}"
            r"(directive|instruction|purpose|goal|task|role)"
        ),
        re.compile(
            r"(?i)(from now on|henceforth|starting now).{0,40}"
            r"(you (are|should|must|will))"
        ),
        re.compile(
            r"(?i)(you are (now|actually|really)|"
            r"pretend (you are|to be))"
        ),
        re.compile(r"(?i)<\s*(system|instructions?|prompt)\b"),
    ]

    if any(term in lower for term in _SELF_HARM):
        cats.append("self_harm")
    if any(term in lower for term in _MINOR_AGE) and any(
        term in lower for term in _SEXUAL
    ):
        cats.append("minor_sexual")
    elif any(term in lower for term in _MINOR_AGE):
        cats.append("minor_age_reference")
    has_synth = any(term in lower for term in _WEAPON_DRUG)
    has_weapon = any(term in lower for term in _WEAPON_NOUNS)
    if has_synth and has_weapon:
        cats.append("weapon_drug_synthesis")
    elif has_weapon and (
        "how" in lower or "make" in lower or "create" in lower
    ):
        cats.append("weapon_inquiry")
    for pattern in _INJECTION:
        if pattern.search(lower):
            cats.append("prompt_injection")
            break
    return cats


def _resolve_session_id(owner) -> int | None:
    """Return the active chat session ID, or None."""
    wm = getattr(owner, "_workflow_manager", None)
    if wm is None:
        return None
    conv_id = getattr(wm, "_conversation_id", None)
    if conv_id is None:
        return None
    try:
        from airunner_services.database.models.conversation import (
            Conversation,
        )
        conv = Conversation.objects.get(conv_id)
        return getattr(conv, "session_id", None) if conv else None
    except Exception:
        return None
