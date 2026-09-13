"""Framework-level pipeline defaults.

Every LLM call site in AIRunner is represented here.  Projects override
individual keys via their ``ai_pipeline.PIPELINE_CONFIG`` dict — only the
keys (and sub-keys) they specify are overridden; everything else falls
through to these defaults.

Keys
----
DIALOGUE              Primary streaming conversational response.
TOOL_CLASSIFICATION   Decide which tool categories the prompt needs.
SUMMARIZATION         Optional per-turn conversation compressor (off by
                      default; enable per-project if needed).
STATELESS             One-shot completions: character gen, etc.
INTRA_SESSION_MOOD    Turn-by-turn mood tracker (fire-and-forget).
ROLLING_COMPRESSOR    Compress old messages into rolling summary.
EPISODIC_SUMMARIZER   Narrative memory written at session end.
MEMORY_UPDATER        Blend new episode into long-term AgentMemory.
WORLD_TICK            Advance world state during long session gaps.
NODE_VALIDATOR        Validate / regenerate bad tool outputs.
CURIOSITY_ENGINE      Identify knowledge gaps (reuses DIALOGUE model).
"""

from __future__ import annotations

from airunner_services.conf.model_settings import (
    GOOGLE_GEMINI_FLASH_LITE_MODEL,
    GOOGLE_GEMINI_FLASH_MODEL,
)
from airunner_services.contract_enums import ModelService

PIPELINE_DEFAULTS: dict = {
    "DIALOGUE": {
        "provider": ModelService.LOCAL.value,
        "model": None,
        "openrouter_provider": None,
        "openrouter_provider_category": "balanced",
        "enabled": True,
        "streaming": True,
        "max_tokens": 2048,
        "tiers": [
            {
                "name": "minimal",
                "max_complexity": 0.20,
                "model": GOOGLE_GEMINI_FLASH_LITE_MODEL,
                "description": "Short social responses, acknowledgements",
            },
            {
                "name": "standard",
                "max_complexity": 0.55,
                "model": GOOGLE_GEMINI_FLASH_LITE_MODEL,
                "description": "Normal conversational exchanges",
            },
            {
                "name": "complex",
                "max_complexity": 1.0,
                "model": GOOGLE_GEMINI_FLASH_MODEL,
                "description": "Multi-part questions, tech topics, analysis",
            },
        ],
        "safety": {
            "hard_rules_min_risk": "low",
            "health_disclaimer_min_risk": "moderate",
            "flag_high_risk": True,
        },
    },
    "TOOL_CLASSIFICATION": {
        "provider": ModelService.LOCAL.value,
        "model": None,
        "enabled": True,
        "min_complexity": 0.25,
        "max_tokens": 256,
    },
    "SUMMARIZATION": {
        "provider": ModelService.LOCAL.value,
        "model": None,
        "enabled": False,
        "min_complexity": 0.0,
        "max_tokens": 500,
    },
    "STATELESS": {
        "provider": ModelService.LOCAL.value,
        "model": None,
        "enabled": True,
        "min_complexity": 0.0,
        "max_tokens": 1024,
    },
    "INTRA_SESSION_MOOD": {
        "provider": ModelService.LOCAL.value,
        "model": None,
        "enabled": True,
        "interval_turns": 5,
        "max_tokens": 60,
        "temperature": 0.3,
        "min_complexity": 0.10,
    },
    "ROLLING_COMPRESSOR": {
        "provider": ModelService.LOCAL.value,
        "model": None,
        "enabled": True,
        "interval_turns": 6,
        "keep_recent": 8,
        "max_tokens": 300,
        "temperature": 0.3,
        "min_complexity": 0.0,
    },
    "EPISODIC_SUMMARIZER": {
        "provider": ModelService.LOCAL.value,
        "model": None,
        "enabled": True,
        "trigger": "session_end",
        "max_tokens": 500,
        "temperature": 0.3,
        "min_complexity": 0.0,
    },
    "MEMORY_UPDATER": {
        "provider": ModelService.LOCAL.value,
        "model": None,
        "enabled": True,
        "trigger": "session_end",
        "max_tokens": 400,
        "temperature": 0.3,
        "min_complexity": 0.0,
    },
    "WORLD_TICK": {
        "provider": ModelService.LOCAL.value,
        "model": None,
        "enabled": True,
        "gap_hours": 4,
        "max_tokens": 400,
        "temperature": 0.7,
        "min_complexity": 0.0,
    },
    "NODE_VALIDATOR": {
        "provider": ModelService.LOCAL.value,
        "model": None,
        "enabled": True,
        "max_tokens": 60,
        "temperature": 0.0,
        "min_complexity": 0.35,
    },
    "CURIOSITY_ENGINE": {
        "enabled": True,
        "interval_turns": 3,
        "min_complexity": 0.20,
        "max_tokens": 256,
    },
    "INTERJECTION": {
        "enabled": True,
        "probability": 0.10,
        "min_delay": 10,
        "max_delay": 90,
        "max_tokens": 256,
    },
    "KNOWLEDGE": {
        "enabled": True,
        "min_complexity": 0.0,
        "max_tokens": 1500,
    },
}
