"""search_email_knowledge — surface synced email data into chat.

The email sync pipeline (contact extraction, body-chunk indexing,
entity/fact resolution) writes ``EmailBodyChunk`` and entity-scoped
``KnowledgeFact`` rows, but nothing previously read them back into a
conversation — ``get_memory_context()`` in the framework's
prompt_builder/context.py implements exactly this retrieval but was
never called from the live prompt-assembly or tool-selection pipeline.
This tool is the wiring: it reuses that same retrieval logic (semantic
search over email body chunks + capitalized-name entity-fact lookup) as
an on-demand, LLM-selectable tool instead of an always-on prompt
injection, matching the existing pattern for conversation recall
(the framework's search_conversations tool).

Email data is scoped to the system bot only (chatbot_id = system bot
id, set by the entity plan) — a non-omnipotent companion chatbot has
no email data to search.
"""

from __future__ import annotations

from typing import Annotated

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


@tool(
    name="search_email_knowledge",
    category=ToolCategory.RECALL,
    description=(
        "Search the user's synced email — thread summaries and known"
        " facts/relationships about people from their inbox. Use this"
        " when the user asks what you know about a specific person"
        " from their email, or about an email topic/thread (job"
        " applications, an order, a project, someone's contact"
        " info). Only useful when acting as the system assistant —"
        " returns nothing for a roleplay/companion chatbot."
    ),
    return_direct=False,
    requires_api=False,
    defer_loading=False,
    keywords=[
        "email", "inbox", "my emails", "in my email",
        "someone from my email", "who emailed me",
    ],
    input_examples=[
        {"query": "job application status with the US government"},
        {"query": "What do you know about Jon Sgaggero?"},
    ],
)
def search_email_knowledge(
    query: Annotated[
        str, "What to search for — a topic, or a person's name."
    ],
) -> str:
    """Search email thread summaries and entity facts for *query*."""
    if not query or not query.strip():
        return "Provide a topic or person's name to search for."

    if not _is_omnipotent():
        return (
            "Email knowledge is only available to the system"
            " assistant, not this chatbot."
        )

    try:
        from airunner_services.knowledge import get_knowledge_base
        from airunner_services.llm.managers.prompt_builder.context import (
            _search_entity_context,
            _search_email_context,
        )

        kb = get_knowledge_base()
        sections: list[str] = []

        entity_lines = _search_entity_context(kb, query)
        if entity_lines:
            sections.append("\n".join(entity_lines))

        email_context = _search_email_context(query)
        if email_context:
            sections.append(email_context)

        if not sections:
            return f"No email knowledge found for '{query}'."
        return "\n\n".join(sections)
    except Exception as exc:
        logger.error("search_email_knowledge failed: %s", exc)
        return f"Error searching email knowledge: {exc}"


def _is_omnipotent() -> bool:
    """Return True when the current chatbot is the system bot with
    omnipotent_knowledge enabled. Mirrors the framework's
    search_conversations.py helper of the same name — email data is
    only ever scoped to the system bot, so this tool is a no-op for
    any other chatbot."""
    try:
        from airunner_services.database.models.chatbot import Chatbot
        from airunner_services.knowledge_context import (
            get_knowledge_chatbot_id,
        )

        chatbot_id = get_knowledge_chatbot_id()
        if chatbot_id is None:
            return False
        chatbot = Chatbot.objects.get(chatbot_id)
        if chatbot is None:
            return False
        return bool(
            getattr(chatbot, "is_system_bot", False)
            and getattr(chatbot, "omnipotent_knowledge", False)
        )
    except Exception:
        return False
