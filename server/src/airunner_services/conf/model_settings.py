"""Shared model identifiers and provider constants.

These are cross-cutting values referenced by both framework code
(``airunner_services``) and project code (``projects/uwuchat``), so
they live under the ``airunner_services`` import root rather than a
project directory — matching how the rest of the framework resolves
imports.
"""

from airunner_services.contract_enums import ModelService

MODEL_PROVIDERS = [
    ModelService.AIRUNNER.value,
    ModelService.LOCAL.value,
    ModelService.GROQ.value,
    ModelService.OPENROUTER.value,
]
MODEL_PROVIDER = ModelService.OPENROUTER.value
CLAUDE_HAIKU_MODEL = "anthropic/claude-haiku-4.5"
GOOGLE_GEMINI_FLASH_MODEL = "google/gemini-2.5-flash"
GOOGLE_GEMINI_FLASH_LITE_MODEL = "google/gemini-2.5-flash-lite"
QWEN_EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
META_LLAMA_INSTRUCT_MODEL = "meta-llama/llama-3.1-8b-instruct"

# OpenRouter slug — routed through OPENROUTER_API_KEY like every
# other UwUChat model, pinned to the native DeepSeek upstream provider
# (see _provider_order_for_model in cloud/llm/model_builders.py).
#
# Dated snapshot (not the rolling "-flash" alias) so the pin doesn't
# silently move onto a different weights revision. Pinned to
# "deepseek" rather than "deepinfra" as of 2026-08-20: DeepInfra had
# zero available endpoints for this model on this OpenRouter account
# (confirmed via /api/v1/chat/completions returning 404 "No endpoints
# found" even though DeepInfra's global endpoint uptime was ~99.6%,
# i.e. an account-side restriction, not a DeepInfra outage) — this was
# the root cause of "Error: An error occurred while contacting the
# model" during code-mode chat. Explicit user override of the
# DeepInfra-only policy in wiki/UwUChat-Pricing-and-Cost-Economics.md
# §6 — that policy exists because DeepSeek's own API is China-hosted,
# so re-litigate before reverting this back to a US-hosted pin.
DEEPSEEK_V4_FLASH_MODEL = "deepseek/deepseek-v4-flash-0731"
