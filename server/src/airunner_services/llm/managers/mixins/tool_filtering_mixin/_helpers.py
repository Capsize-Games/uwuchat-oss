"""Module-level helpers for tool filtering.

Extracted from ``tool_filtering_mixin``.  ``_reconcile_search_research``
keeps the search and research categories bound together.
"""

from __future__ import annotations


def _reconcile_search_research(
    selected_categories: list[str],
) -> list[str]:
    """Ensure search and research categories are both present when either
    is selected.

    search_news (SEARCH) and search_fastsearch_news (RESEARCH) must
    always be available together so the model never has to guess which
    tool name is bound in the current category set.
    """
    if not selected_categories:
        return selected_categories
    has_search = "search" in selected_categories
    has_research = "research" in selected_categories
    if not has_search and not has_research:
        return selected_categories
    result = list(selected_categories)
    if not has_search:
        result.append("search")
    if not has_research:
        result.append("research")
    return result
