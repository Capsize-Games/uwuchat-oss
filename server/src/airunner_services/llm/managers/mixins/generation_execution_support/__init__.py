"""Execution helpers for generation.

Decomposed into focused modules:

- ``_streaming`` — workflow stream loop, callback wiring, CUDA
  preparation, generation-kwarg normalization, message collection
- ``_scheduling`` — retired per-turn scheduling no-ops and
  deep-research diagnostics
- ``_mood`` — intra-session mood computation, client emission,
  and persistence
- ``_scoring`` — per-turn complexity/risk scoring and risk events
- ``_tier`` — complexity-tier DIALOGUE model swapping
- ``_generate`` — ``do_generate`` entry point and model-used events

All module-level names (``do_generate``, ``run_generation_stream``,
``_update_and_emit_mood``, ``_REASONING_MODEL_PREFIXES``, ...) remain
importable from this package so existing importers keep working
unchanged.
"""

from __future__ import annotations

from airunner_services.llm.managers.mixins.generation_execution_support._backend import (
    _REASONING_MODEL_PREFIXES,
    _active_chat_models,
    _has_tool_choice,
    _is_openai_backend,
    _model_supports_reasoning,
)
from airunner_services.llm.managers.mixins.generation_execution_support._generate import (
    _record_model_used_event,
    do_generate,
)
from airunner_services.llm.managers.mixins.generation_execution_support._mood import (
    _emit_mood_to_client,
    _persist_auto_mood,
    _update_and_emit_mood,
)
from airunner_services.llm.managers.mixins.generation_execution_support._scheduling import (
    _log_deep_research_action,
    _maybe_schedule_curiosity,
    _maybe_schedule_extraction,
    _resolve_conversation_id,
    _schedule_mid_session_tasks,
)
from airunner_services.llm.managers.mixins.generation_execution_support._scoring import (
    _compute_turn_scores,
    _maybe_record_risk_flag,
    _resolve_session_id,
    _risk_categories,
)
from airunner_services.llm.managers.mixins.generation_execution_support._streaming import (
    _HF_ONLY_KWARGS,
    _normalize_generation_kwargs,
    _prepare_cuda,
    _stream_generation,
    _stream_messages,
    run_generation_stream,
)
from airunner_services.llm.managers.mixins.generation_execution_support._tier import (
    _apply_dialogue_tier_model,
    _restore_dialogue_model,
)

__all__ = [
    "_HF_ONLY_KWARGS",
    "_REASONING_MODEL_PREFIXES",
    "_active_chat_models",
    "_apply_dialogue_tier_model",
    "_compute_turn_scores",
    "_emit_mood_to_client",
    "_has_tool_choice",
    "_is_openai_backend",
    "_log_deep_research_action",
    "_maybe_record_risk_flag",
    "_maybe_schedule_curiosity",
    "_maybe_schedule_extraction",
    "_model_supports_reasoning",
    "_normalize_generation_kwargs",
    "_persist_auto_mood",
    "_prepare_cuda",
    "_record_model_used_event",
    "_resolve_conversation_id",
    "_resolve_session_id",
    "_restore_dialogue_model",
    "_risk_categories",
    "_schedule_mid_session_tasks",
    "_stream_generation",
    "_stream_messages",
    "_update_and_emit_mood",
    "do_generate",
    "run_generation_stream",
]
