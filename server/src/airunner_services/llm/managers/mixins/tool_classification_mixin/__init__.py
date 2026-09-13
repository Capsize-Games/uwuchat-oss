"""Tool routing heuristics and LLM-assisted classification.

Decomposed into focused modules:

- ``constants`` — module-level trigger/reference tables
- ``heuristics`` — detection helpers (entity/personal/complexity gate)
- ``patterns`` — class-level trigger-word pattern tables
- ``detectors`` — trigger-word detection classmethods
- ``parsing`` — classifier response parsing
- ``streaming`` — streamed classification with thinking support
- ``invocation`` — classification model invocation
- ``classifier`` — the LLM-assisted classification entry point

``ToolClassificationMixin`` is the composed public class; all existing
importers keep working unchanged.
"""

from __future__ import annotations

from airunner_services.llm.managers.mixins.tool_classification_mixin.classifier import (
    ToolClassificationClassifierMixin,
)
from airunner_services.llm.managers.mixins.tool_classification_mixin.constants import (
    _BELOW_MIN_COMPLEXITY,
    _ENTITY_REFERENCE_TRIGGERS,
    _LOOKUP_TOOL_CATEGORY,
    _PERSONAL_LIFE_NOUNS,
    _RECALL_DIRECTIVE_TRIGGERS,
    _REFUSAL_PATTERNS,
    _SEARCH_NEWS_TOOL_NAMES,
    _TERSE_MAX_WORDS,
)
from airunner_services.llm.managers.mixins.tool_classification_mixin.detectors import (
    ToolClassificationDetectorsMixin,
)
from airunner_services.llm.managers.mixins.tool_classification_mixin.heuristics import (
    _below_min_complexity,
    _contains_entity_reference,
    _contains_personal_reference,
    _contains_proper_noun_reference,
    _contains_trigger_word,
    _is_terse,
    _looks_like_refusal,
    _recent_search_in_conversation,
)
from airunner_services.llm.managers.mixins.tool_classification_mixin.invocation import (
    ToolClassificationInvocationMixin,
)
from airunner_services.llm.managers.mixins.tool_classification_mixin.parsing import (
    ToolClassificationParsingMixin,
)
from airunner_services.llm.managers.mixins.tool_classification_mixin.patterns import (
    ToolClassificationPatternsMixin,
)
from airunner_services.llm.managers.mixins.tool_classification_mixin.streaming import (
    ToolClassificationStreamingMixin,
)
from airunner_services.llm.pipeline_loader import pipeline_config


class ToolClassificationMixin(
    ToolClassificationPatternsMixin,
    ToolClassificationDetectorsMixin,
    ToolClassificationParsingMixin,
    ToolClassificationStreamingMixin,
    ToolClassificationInvocationMixin,
    ToolClassificationClassifierMixin,
):
    """Classify prompts into tool categories and direct tool routes."""


__all__ = [
    "ToolClassificationClassifierMixin",
    "ToolClassificationDetectorsMixin",
    "ToolClassificationInvocationMixin",
    "ToolClassificationMixin",
    "ToolClassificationParsingMixin",
    "ToolClassificationPatternsMixin",
    "ToolClassificationStreamingMixin",
    "_BELOW_MIN_COMPLEXITY",
    "_ENTITY_REFERENCE_TRIGGERS",
    "_LOOKUP_TOOL_CATEGORY",
    "_PERSONAL_LIFE_NOUNS",
    "_RECALL_DIRECTIVE_TRIGGERS",
    "_REFUSAL_PATTERNS",
    "_SEARCH_NEWS_TOOL_NAMES",
    "_TERSE_MAX_WORDS",
    "_below_min_complexity",
    "_contains_entity_reference",
    "_contains_personal_reference",
    "_contains_proper_noun_reference",
    "_contains_trigger_word",
    "_is_terse",
    "_looks_like_refusal",
    "_recent_search_in_conversation",
    "pipeline_config",
]
