"""Recall facts the character has established about itself."""

from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

from ._helpers import merge_search_results

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


@tool(
    name="recall_character_facts",
    category=ToolCategory.KNOWLEDGE,
    description=(
        "Search your own memory for facts you've established about yourself "
        "in past conversations. Use when you need to recall a specific detail "
        "about your backstory, preferences, location, or personal history."
    ),
    return_direct=False,
    requires_api=False,
    defer_loading=False,
    keywords=[
        "what do i know about myself",
        "my facts",
        "who am i",
        "what have i said about myself",
        "my backstory",
        "my history",
    ],
    input_examples=[
        {"query": "where do I live"},
        {"query": "my family and relationships"},
        {"query": "my personal history"},
        {"query": "my preferences and hobbies"},
    ],
)
def recall_character_facts(
    query: Annotated[str, "What you're trying to remember about yourself"],
    max_results: Annotated[int, "Maximum facts to return"] = 5,
    api: Any = None,
) -> str:
    """Search the character's self-knowledge base for relevant facts.

    Args:
        query: What to search for.
        max_results: Max results to return.
        api: API instance (injected).

    """
    from airunner_services.knowledge_context import set_knowledge_subject

    set_knowledge_subject("self")
    try:
        from airunner_services.knowledge import get_knowledge_base

        kb = get_knowledge_base()

        agent = api if api and hasattr(api, "search") else None
        rag_results = kb.search_rag(query, k=max_results, agent=agent)
        keyword_results = kb.search(query, max_results=max_results)

        results = merge_search_results(rag_results, keyword_results, [])

        if not results:
            return f"No self-knowledge found for: '{query}'."

        return "\n".join(f"- {fact}" for fact in results[:max_results])

    except Exception as e:
        logger.error("Error recalling character facts: %s", e)
        return f"Error: {str(e)}"
    finally:
        set_knowledge_subject("user")
