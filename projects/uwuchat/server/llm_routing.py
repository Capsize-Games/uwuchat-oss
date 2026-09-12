"""UwUchat LLM model routing configuration.

Maps function keys to provider/model assignments.  Edit this file to
point each function at a different OpenRouter model without touching
framework code.

Keys
----
DIALOGUE           Primary conversational response (streaming).
TOOL_CLASSIFICATION Decide which tool categories the user prompt needs.
SUMMARIZATION      Compress old conversation messages (disabled in UwuChat
                   by default but honoured when re-enabled).
STATELESS          One-shot completions: character generation, etc.

Provider values: "openrouter" | "local" | "ollama" | "openai"
Model values   : OpenRouter model string, e.g. "meta-llama/llama-3.1-8b-instruct"

TODO: revisit per-task model mix — see internal-docs/STRATEGIC_PLAN.md
Phase 2 section.
"""

from airunner_services.conf.model_settings import (
    CLAUDE_HAIKU_MODEL,
    META_LLAMA_INSTRUCT_MODEL,
    MODEL_PROVIDER,
)


MODEL_ROUTING: dict = {
    "DIALOGUE": {
        "provider": MODEL_PROVIDER,
        "model": CLAUDE_HAIKU_MODEL,
    },
    "TOOL_CLASSIFICATION": {
        "provider": MODEL_PROVIDER,
        "model": META_LLAMA_INSTRUCT_MODEL,
    },
    "SUMMARIZATION": {
        "provider": MODEL_PROVIDER,
        "model": META_LLAMA_INSTRUCT_MODEL,
    },
    "STATELESS": {
        "provider": MODEL_PROVIDER,
        "model": META_LLAMA_INSTRUCT_MODEL,
    },
}
