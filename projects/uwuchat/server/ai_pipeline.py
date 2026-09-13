"""UwUchat AI pipeline configuration.

This is the single place to change models, providers, and task behaviour
for the UwUchat deployment.  Only keys (and sub-keys) listed here
override the framework defaults in
``airunner_services.llm.pipeline_defaults.PIPELINE_DEFAULTS``.

PII masking
-----------
Text sent to the LLM provider is masked by the
``airunner_services.llm.pii`` package (see
``plans/uwuchat-pii-masking-before-llm.md`` for architecture).
Personally identifiable information (names, emails, phone numbers,
etc.) is replaced with placeholders before egress and restored
server-side before the response reaches the client.

Provider note
-------------
``provider`` is always ``"openrouter"`` for UwUchat (cloud-only).
The ``openrouter_provider`` field selects a specific upstream host (e.g.
``"Google AI Studio"``); leave ``None`` to let OpenRouter auto-route.
``openrouter_provider_category`` controls routing mode:
  - ``"balanced"``  price + speed trade-off (default)
  - ``"nitro"``     lowest latency
  - ``"exacto"``    fixed provider (requires openrouter_provider set)

OpenRouter model strings: https://openrouter.ai/models

Cost note (2026-07-27, provider pin revised 2026-08-20)
--------------------------------------------------------
EXPERIMENT: every text-generation pipeline below (previously a mix of
claude-haiku-4.5 and gemini-2.5-flash) is temporarily pointed at
deepseek/deepseek-v4-flash-0731 via OpenRouter — see
wiki/UwUChat-Pricing-and-Cost-Economics.md §6 for the pricing
research. EMBEDDING is unaffected — it's a different model category
(qwen3-embedding-8b) and was never a candidate.

Provider pin (see _provider_order_for_model in
cloud/llm/model_builders.py): originally pinned to DeepInfra (US-
incorporated host, no Chinese-hosted inference — see
feedback_no_chinese_hosted_providers in project memory). Moved to the
native "deepseek" provider on 2026-08-20 by explicit user override
after DeepInfra started returning "no endpoints" for this OpenRouter
account (account-side restriction, not a DeepInfra outage) — this was
the direct cause of code-mode chat failing with "Error: An error
occurred while contacting the model". The native provider is
China-hosted, which trades away the original US-host requirement;
re-litigate before treating this as permanent, and see
DEEPSEEK_V4_FLASH_MODEL in conf/model_settings.py.

This was done in one pass across all pipelines rather than the
incremental per-pipeline testing DIALOGUE and KNOWLEDGE got
individually — verify each pipeline's actual output quality
(especially KNOWLEDGE's fact-extraction accuracy and TOOL_CLASSIFICATION's
category-selection reliability; both were previously moved to a
pricier model specifically for a quality reason recorded in the
comments below) before treating this as a permanent switch. To
revert one pipeline, re-import CLAUDE_HAIKU_MODEL or
GOOGLE_GEMINI_FLASH_MODEL from
``airunner_services.conf.model_settings`` and set its "model" value
back.

To swap any model, change its ``"model"`` value here and restart.

Env-driven provider/model (LAN stacks)
--------------------------------------
``AIRUNNER_LLM_PROVIDER`` and ``AIRUNNER_LLM_MODEL`` override the
provider and model for every *text-generation* pipeline below
(defaulting to ``MODEL_PROVIDER`` / ``DEEPSEEK_V4_FLASH_MODEL`` when
unset, so cloud behavior is byte-identical).  The ``EMBEDDING`` entry
is deliberately excluded — embeddings never go through the
ChatModelFactory; ``embedding_provider.py`` reads that entry for the
model name only and posts to OpenRouter (decision D2 of
``plans/lan-shared-edge-inference.md``).
"""

import os

from airunner_services.conf.model_settings import (
    DEEPSEEK_V4_FLASH_MODEL,
    MODEL_PROVIDER,
    QWEN_EMBEDDING_MODEL,
)

PROVIDER = os.getenv("AIRUNNER_LLM_PROVIDER", MODEL_PROVIDER)
DIALOGUE_MODEL = os.getenv("AIRUNNER_LLM_MODEL", DEEPSEEK_V4_FLASH_MODEL)


PIPELINE_CONFIG: dict = {
    # ------------------------------------------------------------------ #
    #  Main dialogue flow                                                  #
    # ------------------------------------------------------------------ #
    # EXPERIMENT (2026-07-27): DIALOGUE temporarily pointed at DeepSeek
    # V4 Flash via OpenRouter, pinned to the native "deepseek"
    # upstream provider as of 2026-08-20 (see _provider_order_for_model
    # in cloud/llm/model_builders.py — was DeepInfra until it started
    # 404ing for this account) — evaluating cost/quality vs. Claude
    # Haiku 4.5. Uses the existing OPENROUTER_API_KEY. See
    # wiki/UwUChat-Pricing-and-Cost-Economics.md §6 for the research
    # behind this pick.
    # Revert: set "provider" back to MODEL_PROVIDER and "model" back
    # to CLAUDE_HAIKU_MODEL on all four entries below.
    # EXPERIMENT (2026-07-28): DIALOGUE max_tokens raised from
    # default 500 to 2000 to test whether DeepSeek's empty
    # post-grounding responses are a token-budget ceiling issue.
    # Revert to remove "max_tokens" entirely (back to default 500)
    # if the diagnostic shows finish_reason="stop" with tokens well
    # under any cap.
    "DIALOGUE": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
        "max_tokens": 2000,
        "tiers": [
            {
                "name": "minimal",
                "max_complexity": 0.20,
                "model": DIALOGUE_MODEL,
                "description": "Short social responses, acknowledgements",
            },
            {
                "name": "standard",
                "max_complexity": 0.55,
                "model": DIALOGUE_MODEL,
                "description": "Normal conversational exchanges",
            },
            {
                "name": "complex",
                "max_complexity": 1.0,
                "model": DIALOGUE_MODEL,
                "description": "Multi-part questions, tech topics, analysis",
            },
        ],
    },
    # Prompt-rewrite stage: runs BEFORE TOOL_CLASSIFICATION on the
    # same cheap-tier model.  Detects prompts that will collide with
    # pipeline limits (e.g. asking for dozens of independently-sourced
    # items) and rewrites them internally before tooling decides which
    # categories apply.  Must not add meaningful cost — one small
    # classification call per turn.
    "PROMPT_REWRITE": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
        "max_tokens": 256,
        "temperature": 0.0,
    },
    "TOOL_CLASSIFICATION": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
    },
    # Cheap-model tool-execution stage: runs between TOOL_CLASSIFICATION
    # and DIALOGUE to execute system/math/research/search tool calls on a
    # cheap model, reserving Haiku purely for in-character reply narration.
    "TOOL_EXECUTION": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
        "max_tokens": 1024,
    },
    "SUMMARIZATION": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
        "enabled": False,
    },
    "STATELESS": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
    },
    # Character name/personality/backstory/greeting generation
    # (POST /api/v1/llm/generate-character and
    # /api/v1/llm/generate-uwu-identity).  The LLM call itself is
    # served by the STATELESS pipeline's model (stateless one-shot
    # completion), so keep "model" in sync with STATELESS — this key
    # exists to attribute the spend in pipeline_token_usage.
    "CHARACTER_CREATION": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
    },
    # Knowledge extraction (save_fact/check_similar_facts/retract_fact).
    # EXPERIMENT (2026-07-27): temporarily pointed at DeepSeek V4 Flash
    # (same OpenRouter+deepseek-native pin as DIALOGUE) to evaluate cost vs.
    # quality. IMPORTANT: this pipeline was previously moved *away*
    # from a cheap model (Gemini) specifically because its fact-
    # extraction/dedup judgment was noticeably worse than Haiku's (see
    # the note retained below). That is exactly the failure mode to
    # check for here — verify actual extracted-fact accuracy and
    # duplicate handling, not just conversational quality, before
    # trusting this beyond a local experiment.
    # Revert: set "provider" back to MODEL_PROVIDER and "model" back
    # to CLAUDE_HAIKU_MODEL.
    #
    # Switched to Haiku 2026-07: the save_fact batching fix (one call per
    # turn instead of one per fact) cut per-turn token volume enough that
    # Haiku's higher per-token price no longer dominates, and its fact
    # extraction/dedup judgment is noticeably better than gemini-2.5-flash.
    "KNOWLEDGE": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
    },

    # ------------------------------------------------------------------ #
    #  Embeddings (cloud-only — replaces local e5-large)                  #
    # ------------------------------------------------------------------ #
    # Uses OpenRouter's OpenAI-compatible /v1/embeddings endpoint.
    # Pinned to DeepInfra specifically (zero data retention, lower
    # cost) in embedding_provider.py's request-level provider routing
    # — openai/text-embedding-3-large was blocked outright by this
    # account's OpenAI Zero-Data-Retention privacy setting, which has
    # no compatible OpenRouter-routed endpoint for that model.
    "EMBEDDING": {
        "provider": MODEL_PROVIDER,
        "model": QWEN_EMBEDDING_MODEL,
    },

    # ------------------------------------------------------------------ #
    #  Background tasks                                                    #
    # ------------------------------------------------------------------ #

    # Updates the chatbot's mood from the full session arc at
    # session-end.  More meaningful than per-5-turns snapshots.
    "INTRA_SESSION_MOOD": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
        "enabled": True,
        "trigger": "session_end",
        "temperature": 0.8,
    },

    # Compresses the cold session's messages into a rolling summary.
    # Fires during session rotation (4h+ gap).  Uses a cheap LLM.
    "ROLLING_COMPRESSOR": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
        "enabled": True,
        "trigger": "session_end",
        "keep_recent": 8,
    },

    # Writes a narrative memory entry when a session ends (4h gap).
    # Fires as a background asyncio task during session rotation — not a
    # timer/cron.  The LLM call is separate from the main DIALOGUE stream.
    "EPISODIC_SUMMARIZER": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
        "trigger": "session_end",
    },

    # Blends the new episode into the chatbot's long-term AgentMemory.
    # Cascaded from EPISODIC_SUMMARIZER after the summary is persisted.
    "MEMORY_UPDATER": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
        "trigger": "session_end",
    },

    # DISABLED — post-turn interjections ("oh wait, one more thing…")
    # are inherently mid-conversation and don't make sense at session-end.
    "INTERJECTION": {
        "enabled": False,
    },

    # REMOVED — world simulation was an abandoned prototype.
    # "WORLD_TICK" is no longer configured.

    # Validates tool output; regenerates if response violates constraints.
    "NODE_VALIDATOR": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
    },

    # Runs at session-end to identify one knowledge gap / curiosity
    # question seeded from the full session arc.  Injected as a
    # welcome-back question on the next turn.
    "CURIOSITY_ENGINE": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
        "enabled": True,
        "trigger": "session_end",
    },

    # Writes a first-person journal entry from the day's conversation
    # when the UwU decides the moment is right (mid-conversation tool
    # call).  Uses the cheap summarization model.
    "JOURNAL_SUMMARIZER": {
        "provider": PROVIDER,
        "model": DIALOGUE_MODEL,
        "enabled": True,
        "max_tokens": 500,
    },

    # ------------------------------------------------------------------ #
    #  Tool availability                                                    #
    # ------------------------------------------------------------------ #

    # UwUchat has no user-facing "conversations" concept — sessions
    # auto-rotate on a 4h gap and render as one continuous append-only
    # thread (see CLAUDE.md). The framework's conversation-management
    # tools (clear_chat_history, get_conversation_summary,
    # load_conversation) assume a conventional multi-conversation chat
    # UI that doesn't exist here, so the UwU must never be able to call
    # them. Hard-disabled here rather than relying on the tool
    # classifier simply never selecting "conversation".
    #
    # "image" is also hard-disabled: UwUchat's system bot has no image
    # generation feature, and this blocks both the keyword-trigger and
    # LLM-classifier selection paths in one place.
    "TOOL_CATEGORIES": {
        "disabled": ["conversation", "image"],
    },
}
