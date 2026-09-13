"""
List knowledge files tool.

Lists all knowledge files in the knowledge base, newest first.
"""

from airunner_services.llm.core.tool_registry import tool, ToolCategory
from airunner_services.settings import AIRUNNER_LOG_LEVEL
from airunner_services.utils.application import get_logger

logger = get_logger(__name__, AIRUNNER_LOG_LEVEL)


@tool(
    name="list_knowledge_files",
    category=ToolCategory.KNOWLEDGE,
    description=(
        "List all dates that have stored knowledge facts. "
        "Shows dates with fact counts, newest first."
    ),
    return_direct=False,
    requires_api=False,
    keywords=["list", "files", "dates", "history", "knowledge"],
    input_examples=[],
)
def list_knowledge_files() -> str:
    """List all knowledge dates."""
    try:
        from airunner_services.knowledge import get_knowledge_base

        kb = get_knowledge_base()
        entries = kb.list_files()

        if not entries:
            return (
                "No knowledge recorded yet. "
                "Use record_knowledge to start recording facts."
            )

        total_facts = sum(e["count"] for e in entries)
        output = (
            f"Knowledge dates ({len(entries)} dates, "
            f"{total_facts} facts total):\n\n"
        )
        for e in entries[:20]:
            date_str = e["date"]
            count = e["count"]
            size = e["size_bytes"]
            output += f"• {date_str} — {count} facts ({size} bytes)\n"

        if len(entries) > 20:
            output += f"\n... and {len(entries) - 20} more dates"

        return output

    except Exception as e:
        logger.error(f"Error listing knowledge: {e}")
        return f"Error: {str(e)}"
