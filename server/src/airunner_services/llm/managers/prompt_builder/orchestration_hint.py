"""Tool-discovery instructions.

Tells the model to use the always-available search_tools meta-tool
when it needs a capability outside its currently-bound tool set,
instead of just telling the user it can't help.  search_tools uses
BM25 to find matching deferred tools and automatically binds them
for the next turn without category-swap churn.  Framework-level and
tier-independent.
"""

from __future__ import annotations

from typing import Optional

ORCHESTRATION_INSTRUCTIONS = (
    "TOOL DISCOVERY: Your current tools were pre-selected for this"
    " message and may not include what you actually need. Before"
    " telling the user you can't do something (search a data source,"
    " perform an action, look something up), call search_tools with"
    " a short query describing what you need — it will find matching"
    " tools and make them available on your very next turn. Only"
    " tell the user you can't help after confirming no tool covers it."
)


def orchestration_hint_part(owner) -> Optional[str]:
    """Return the tool-recovery instructions when tools are bound."""
    if not getattr(owner, "_tools", None):
        return None
    return ORCHESTRATION_INSTRUCTIONS
