"""Cloud LLM provider configuration — API-based model lists.

This module contains the model lists for OpenRouter and Ollama. It is
the cloud counterpart of :mod:`airunner_services.edge.llm.providers`.
"""

from __future__ import annotations

from typing import List

# ------------------------------------------------------------------
# OpenRouter model list
# ------------------------------------------------------------------

OPENROUTER_MODELS: List[str] = [
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3-opus",
    "openai/gpt-4-turbo",
    "openai/gpt-4",
    "openai/gpt-3.5-turbo",
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "google/gemini-pro-1.5",
    "mistralai/mistral-large",
    "custom",
]

# ------------------------------------------------------------------
# Ollama model list
# ------------------------------------------------------------------

OLLAMA_MODELS: List[str] = [
    "llama3.2",
    "llama3.1",
    "llama3",
    "mistral",
    "mixtral",
    "phi3",
    "qwen2.5",
    "qwen3",
    "qwen3:8b",
    "qwen3:14b",
    "qwen3:30b-a3b",
    "qwen3:32b",
    "qwen3-coder:30b-a3b",
    "codellama",
    "custom",
]
