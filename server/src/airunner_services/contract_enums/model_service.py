"""LLM service backends persisted in settings."""

from enum import Enum


class ModelService(Enum):
    """LLM service backends persisted in settings."""

    AIRUNNER = "airunner"
    GROQ = "groq"
    LOCAL = "local"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    OPENAI = "openai"
    DEEPINFRA = "deepinfra"
    GOOGLE = "google"
    QWEN = "qwen"
