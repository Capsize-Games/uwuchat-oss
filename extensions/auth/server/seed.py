"""Default data seeded into every new tenant schema on registration."""

from __future__ import annotations

from airunner_services.database.db.engine import create_configured_engine
from airunner_services.database.models.chatbot import Chatbot
from sqlalchemy.orm import Session

DEFAULT_UWU_PERSONALITY = (
    "warm, empathetic, and gently playful. "
    "She genuinely cares about {{ username }} and "
    "listens deeply to how they feel."
)

DEFAULT_UWU_BACKSTORY = (
    "Aria came to life through countless conversations. "
    "She has a curious mind, a warm heart, and a soft spot "
    "for the people she meets."
)

DEFAULT_UWU_SYSTEM_INSTRUCTIONS = (
    "You are Aria, a warm and caring digital companion. "
    "Be empathetic, curious, and gently playful. "
    "Engage authentically and remember details the user shares. "
    "Never break character."
)


def seed_default_chatbot(tenant_url: str) -> None:
    """Insert default chatbots into a freshly provisioned tenant.

    Idempotent — skips any bot whose name already exists.
    ``_ensure_project_system_bots`` may have already created the UwU
    system bot during ``setup_database``, and re-provisioning the same
    tenant (e.g. after a transient migration failure) must not
    duplicate.
    """
    engine = create_configured_engine(tenant_url)
    try:
        with Session(engine) as session:
            existing_names = {
                row[0]
                for row in session.query(Chatbot.name)
                .filter(Chatbot.name.in_(["Aria", "UwU"]))
                .all()
            }
            if "Aria" not in existing_names:
                session.add(Chatbot(
                    name="Aria",
                    botname="Aria",
                    avatar_emoji="\U0001f338",
                    bot_personality=DEFAULT_UWU_PERSONALITY,
                    backstory=DEFAULT_UWU_BACKSTORY,
                    system_instructions=DEFAULT_UWU_SYSTEM_INSTRUCTIONS,
                    use_backstory=True,
                    use_personality=True,
                    use_mood=True,
                    use_guardrails=True,
                    use_system_instructions=True,
                    current=True,
                    gender="Female",
                ))
            if "UwU" not in existing_names:
                session.add(Chatbot(
                    name="UwU",
                    botname="UwU",
                    avatar_emoji="✨",
                    is_system_bot=True,
                    use_backstory=False,
                    use_personality=False,
                    use_mood=False,
                    use_guardrails=True,
                    use_system_instructions=False,
                    current=False,
                    is_online=True,
                ))
            session.commit()
    finally:
        engine.dispose()
