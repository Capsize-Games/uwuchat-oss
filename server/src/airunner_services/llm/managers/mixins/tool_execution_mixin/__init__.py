"""Tool execution mixin for WorkflowManager.

Handles tool execution with status tracking and workflow event sinks.

Decomposed into focused modules:

- ``_core`` — lifecycle init, forced-tool policy, deferred tool loading
- ``_execution`` — the ToolNode execution orchestrator
- ``_dedup`` — single-call tool duplicate interception and usage tracking
- ``_category_switch`` — switch_tool_category prebind/rebind logic
- ``_grounding`` — search-tool result capture for check_grounding
- ``_status`` — starting/completed status emission and mood restore
- ``_details`` — tool call/result detail extraction for the UI

``ToolExecutionMixin`` is the composed public class; all existing
importers keep working unchanged.
"""

from __future__ import annotations

from airunner_services.llm.managers.mixins.tool_execution_mixin._category_switch import (
    ToolExecutionCategorySwitchMixin,
)
from airunner_services.llm.managers.mixins.tool_execution_mixin._core import (
    ToolExecutionCoreMixin,
)
from airunner_services.llm.managers.mixins.tool_execution_mixin._dedup import (
    ToolExecutionDedupMixin,
)
from airunner_services.llm.managers.mixins.tool_execution_mixin._details import (
    ToolExecutionDetailsMixin,
)
from airunner_services.llm.managers.mixins.tool_execution_mixin._execution import (
    _record_search_tools_discoveries,
)
from airunner_services.llm.managers.mixins.tool_execution_mixin._execution import (
    ToolExecutionNodeMixin,
)
from airunner_services.llm.managers.mixins.tool_execution_mixin._grounding import (
    ToolExecutionGroundingMixin,
)
from airunner_services.llm.managers.mixins.tool_execution_mixin._status import (
    ToolExecutionStatusMixin,
)


class ToolExecutionMixin(
    ToolExecutionCoreMixin,
    ToolExecutionNodeMixin,
    ToolExecutionDedupMixin,
    ToolExecutionCategorySwitchMixin,
    ToolExecutionGroundingMixin,
    ToolExecutionStatusMixin,
    ToolExecutionDetailsMixin,
):
    """Manages tool execution with status tracking and signal emission."""


__all__ = [
    "ToolExecutionCategorySwitchMixin",
    "ToolExecutionCoreMixin",
    "ToolExecutionDedupMixin",
    "ToolExecutionDetailsMixin",
    "ToolExecutionGroundingMixin",
    "ToolExecutionMixin",
    "ToolExecutionNodeMixin",
    "ToolExecutionStatusMixin",
    "_record_search_tools_discoveries",
]
