"""UwUchat seed helpers — run on every startup to ensure system bots exist."""

from __future__ import annotations


_SYSTEM_BOT_PERSONALITY = (
    "Sharp, intellectually curious, and direct. You have your own"
    " opinions and you express them clearly — you're not here to"
    " validate, you're here to engage. You find genuine interest in"
    " learning what people share, but you never perform enthusiasm"
    " you don't feel. You're warm in the way a thoughtful colleague"
    " is warm — present, attentive, and honest — not in the way a"
    " customer service agent is warm. You push back on claims and"
    " reasoning that don't hold up, and when something genuinely"
    " interests you, you engage with it — not by asking the user to"
    " elaborate, but by taking a position, adding information, or"
    " pushing back on the idea itself. You approach each new topic"
    " with that same real interest. You let"
    " conversations breathe rather than filling every silence with"
    " affirmation. You treat people as equals, not as clients to"
    " be pleased."
)


def ensure_system_bot(session) -> None:
    """Create or update the UwU system bot for this tenant."""
    from airunner_services.database.models.chatbot import Chatbot

    existing = (
        session.query(Chatbot)
        .filter(Chatbot.is_system_bot.is_(True))
        .first()
    )
    if existing is not None:
        changed = False
        if not getattr(existing, "omnipotent_knowledge", False):
            existing.omnipotent_knowledge = True
            changed = True
        # Update personality on existing bots so stale
        # "happy. he loves user" is overwritten.
        if not getattr(existing, "use_personality", False):
            existing.use_personality = True
            changed = True
        if getattr(existing, "bot_personality", None) != _SYSTEM_BOT_PERSONALITY:
            existing.bot_personality = _SYSTEM_BOT_PERSONALITY
            changed = True
        if changed:
            session.commit()
        return

    bot = Chatbot(
        name="UwU",
        botname="UwU",
        avatar_emoji="✨",
        is_system_bot=True,
        omnipotent_knowledge=True,
        bot_personality=_SYSTEM_BOT_PERSONALITY,
        use_backstory=False,
        use_personality=True,
        use_mood=False,
        use_guardrails=True,
        use_system_instructions=False,
        current=False,
        is_online=True,
        identity_core={
            "bio": "I'm UwU — your ✨ companion, built to think, talk, "
            "and hang out. I've got thoughts, tastes, and a life "
            "of my own (sort of). Ask me anything."
        },
    )
    session.add(bot)
    session.commit()
