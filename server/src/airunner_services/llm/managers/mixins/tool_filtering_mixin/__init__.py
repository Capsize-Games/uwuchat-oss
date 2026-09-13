"""Tool filter application and interruption helpers.

Decomposed into focused modules:

- ``_plan`` — tool-selection plan construction, auto-selection,
  normalization, and tool_choice resolution
- ``_cap`` — cross-turn tool binding with LRU cap and plan
  application
- ``_interrupt`` — interrupt and section-change handling
- ``_helpers`` — module-level helper functions

``ToolFilteringMixin`` is the composed public class; all existing
importers keep working unchanged.
"""

from __future__ import annotations

from airunner_services.llm.managers.mixins.tool_filtering_mixin._auto import (
    ToolFilterAutoMixin,
)
from airunner_services.llm.managers.mixins.tool_filtering_mixin._cap import (
    ToolFilterApplyMixin,
)
from airunner_services.llm.managers.mixins.tool_filtering_mixin._helpers import (
    _reconcile_search_research,
)
from airunner_services.llm.managers.mixins.tool_filtering_mixin._interrupt import (
    ToolFilterInterruptMixin,
)
from airunner_services.llm.managers.mixins.tool_filtering_mixin._normalize import (
    ToolFilterNormalizeMixin,
)
from airunner_services.llm.managers.mixins.tool_filtering_mixin._plan import (
    _KNOWLEDGE_WRITE_TOOL_NAMES,
    _NATIVE_ROUTING_CATEGORIES,
    ToolFilterPlanMixin,
)
from airunner_services.llm.pipeline_loader import pipeline_config


class ToolFilteringMixin(
    ToolFilterAutoMixin,
    ToolFilterPlanMixin,
    ToolFilterNormalizeMixin,
    ToolFilterApplyMixin,
    ToolFilterInterruptMixin,
):
    """Apply per-request tool filtering to the workflow manager."""


__all__ = [
    "ToolFilterApplyMixin",
    "ToolFilterAutoMixin",
    "ToolFilterInterruptMixin",
    "ToolFilterNormalizeMixin",
    "ToolFilteringMixin",
    "ToolFilterPlanMixin",
    "_KNOWLEDGE_WRITE_TOOL_NAMES",
    "_NATIVE_ROUTING_CATEGORIES",
    "_reconcile_search_research",
    "pipeline_config",
]
