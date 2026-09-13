"""
Delete knowledge tool.

Removes facts from the knowledge base by text or regex match.
"""

from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import tool, ToolCategory
from airunner_services.contract_enums import SignalCode
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)

# Blast-radius limit: a single delete call may affect at most this
# many facts.  Exceeding it requires a narrower pattern or a
# specific-ID approach.
_MAX_DELETE_COUNT = 5


@tool(
    name="delete_knowledge",
    category=ToolCategory.KNOWLEDGE,
    description=(
        "Delete a fact from the knowledge base. "
        "Removes lines containing the specified text (or regex match). "
        "Searches all knowledge files unless a specific date is given."
    ),
    return_direct=False,
    requires_api=False,
    keywords=["delete", "remove", "forget", "erase", "clear"],
    input_examples=[
        {"text": "User lives in Seattle"},
        {"text": r".*outdated fact.*", "is_regex": True},
    ],
)
def delete_knowledge(
    text: Annotated[str, "Text or regex pattern to find and delete"],
    date: Annotated[
        str | None,
        "Specific date (YYYY-MM-DD) or None to search all files",
    ] = None,
    is_regex: Annotated[bool, "Treat text as regex pattern"] = False,
    api: Any = None,
) -> str:
    """Delete facts containing the specified text.

    Args:
        text: Text to find and delete.
        date: Specific date or None for all files.
        is_regex: Use regex matching.
        api: API instance.

    Safety gate: before committing, a dry-run count is performed.
    If the pattern would match more than ``_MAX_DELETE_COUNT`` facts,
    the call is rejected with a message asking for a narrower pattern.
    """
    try:
        from airunner_services.knowledge import get_knowledge_base

        kb = get_knowledge_base()

        # ── Blast-radius check (dry-run count before commit) ────
        _, match_count = kb.delete_fact(
            text, date_str=date, is_regex=is_regex, dry_run=True,
        )
        if match_count > _MAX_DELETE_COUNT:
            return (
                f"That would delete {match_count} facts "
                f"(safety limit is {_MAX_DELETE_COUNT}). "
                f"Please use a more specific pattern or delete "
                f"individual facts by ID."
            )

        success, count = kb.delete_fact(
            text, date_str=date, is_regex=is_regex,
        )

        if not success:
            return f"Text not found: '{text}'"

        if api and hasattr(api, "emit_signal"):
            api.emit_signal(
                SignalCode.KNOWLEDGE_FACT_DELETED,
                {"deleted": True, "count": count},
            )
        return f"✓ Deleted {count} fact(s)"

    except Exception as e:
        logger.error(f"Error deleting knowledge: {e}")
        return f"Error: {str(e)}"
