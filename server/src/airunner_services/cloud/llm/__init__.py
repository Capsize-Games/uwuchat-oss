"""Cloud LLM package — API-based LLM inference providers."""

from __future__ import annotations

from airunner_services.cloud.llm.model_builders import (
    create_ollama_model,
    create_openai_model,
    create_openrouter_model,
)
from airunner_services.cloud.llm.ollama_adapter import OllamaAdapter
from airunner_services.cloud.llm.openai_adapter import OpenAIAdapter
from airunner_services.cloud.llm.openrouter_adapter import (
    OpenRouterAdapter,
)
from airunner_services.cloud.llm.provider_creation import (
    create_provider_model_from_runtime,
)
from airunner_services.cloud.llm.providers import (
    OLLAMA_MODELS,
    OPENROUTER_MODELS,
)

__all__ = [
    "OLLAMA_MODELS",
    "OllamaAdapter",
    "OPENROUTER_MODELS",
    "OpenAIAdapter",
    "OpenRouterAdapter",
    "create_ollama_model",
    "create_openai_model",
    "create_openrouter_model",
    "create_provider_model_from_runtime",
]
