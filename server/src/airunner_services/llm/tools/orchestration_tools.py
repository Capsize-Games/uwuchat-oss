"""Meta-tools for category browsing and switching.

These tools are always available regardless of the auto-selected tool
category, giving the model a recovery path when the keyword heuristic
picks the wrong category.
"""

import json
import re
from typing import Annotated

from airunner_services.llm.core.tool_registry import tool, ToolCategory


def _parse_category_descriptions() -> dict[str, str]:
    """Parse one-line category descriptions from ToolCategory's docstring.

    Returns a dict mapping category value strings (e.g. "research") to
    their human-readable description lines.
    """
    doc = ToolCategory.__doc__ or ""
    descriptions: dict[str, str] = {}
    for line in doc.splitlines():
        match = re.match(
            r"\s*-\s+([A-Z_]+):\s*(.+)",
            line,
        )
        if match:
            name = match.group(1).strip()
            desc = match.group(2).strip()
            try:
                member = ToolCategory[name]
                descriptions[member.value] = desc
            except KeyError:
                pass
    return descriptions


def _disabled_categories() -> set[str]:
    """Return the set of category value strings disabled by the project.

    NOTE: This duplicates ToolFilteringMixin._disabled_tool_categories()
    (tool_filtering_mixin.py:~366).  Extracting a shared helper would be
    cleaner but would require restructuring beyond the scope of this
    task — keep both in sync manually for now.
    """
    try:
        from airunner_services.llm.pipeline_loader import (
            pipeline_config,
        )
    except ImportError:
        return set()
    disabled = pipeline_config("TOOL_CATEGORIES").get("disabled", [])
    return {str(c).lower() for c in disabled}


def _enabled_category_descriptions() -> dict[str, str]:
    """Return category descriptions filtered to enabled categories only."""
    all_descriptions = _parse_category_descriptions()
    disabled = _disabled_categories()
    return {
        name: desc
        for name, desc in all_descriptions.items()
        if name not in disabled
    }


@tool(
    name="list_tool_categories",
    category=ToolCategory.ORCHESTRATION,
    description=(
        "List all available tool categories and their descriptions. "
        "Use this to see what kinds of tools you have access to before "
        "deciding which category to switch to."
    ),
    return_direct=False,
    defer_loading=False,
    keywords=["categories", "category", "list tools", "available"],
)
def list_tool_categories() -> str:
    """Return available tool categories with descriptions.

    Disabled categories (set per-project in ai_pipeline.py) are excluded
    from the listing, matching the behaviour of the keyword and LLM-
    classifier selection paths.
    """
    descriptions = _enabled_category_descriptions()
    return json.dumps(
        {
            "categories": [
                {"name": name, "description": desc}
                for name, desc in sorted(descriptions.items())
            ],
            "total": len(descriptions),
            "hint": (
                "Use switch_tool_category(category) to switch to one "
                "of the listed categories."
            ),
        },
        indent=2,
    )


@tool(
    name="switch_tool_category",
    category=ToolCategory.ORCHESTRATION,
    description=(
        "Switch the current tool set to a different category. "
        "Call this when you need tools from a category that isn't "
        "currently available. Use list_tool_categories first to see "
        "what categories exist."
    ),
    return_direct=False,
    defer_loading=False,
    keywords=["switch", "change", "category", "tools"],
    input_examples=[
        {"category": "research"},
        {"category": "knowledge"},
        {"category": "system"},
        {"category": "math"},
    ],
)
def switch_tool_category(
    category: Annotated[
        str,
        "The category name to switch to (e.g. 'research', "
        "'knowledge', 'math'). Must be one of the names returned by "
        "list_tool_categories.",
    ],
) -> str:
    """Attempt to switch to the named tool category.

    Validates the category name against the enabled category set.
    Returns a JSON result indicating success or failure — the actual
    rebinding of tools is handled by the framework's tool-execution
    loop after this function returns.
    """
    category = (category or "").strip().lower()
    if not category:
        return json.dumps({
            "success": False,
            "error": (
                "No category name provided. Use list_tool_categories "
                "to see available categories."
            ),
        })

    enabled = _enabled_category_descriptions()
    if category not in enabled:
        available = sorted(enabled.keys())
        return json.dumps({
            "success": False,
            "error": (
                f"Unknown or disabled category: '{category}'. "
                f"Available categories: {', '.join(available)}"
            ),
        })

    return json.dumps({
        "success": True,
        "category": category,
        "message": (
            f"Switched to '{category}' category. "
            f"You can now use tools from this category."
        ),
    })
