"""Helper functions for ChatModelFactory settings resolution."""

from __future__ import annotations

import os
from typing import Any

from airunner_services.llm.runtime_config import (
    LocalRuntimeConfig,
    ProviderRuntimeConfig,
)

from airunner_services.contract_enums import ModelService


def get_db_settings() -> Any:
    """Return persisted LLM generator settings when available."""
    from airunner_services.database.models.llm_generator_settings import (
        LLMGeneratorSettings,
    )

    return LLMGeneratorSettings.objects.first()


def _dtype_to_quantization_bits(dtype: Any) -> int:
    """Map one persisted dtype value to the legacy quantization selector."""
    mapping = {
        "2bit": 2,
        "4bit": 4,
        "8bit": 8,
    }
    return mapping.get(str(dtype or "").strip().lower(), 0)


def get_quantization_bits(db_settings: Any) -> int:
    """Resolve quantization preference from persisted service settings."""
    if db_settings is None:
        return 0

    db_quant = getattr(db_settings, "quantization_bits", None)
    if db_quant is not None:
        try:
            return int(db_quant)
        except (TypeError, ValueError):
            pass

    return _dtype_to_quantization_bits(getattr(db_settings, "dtype", None))


def get_enable_thinking(
    db_settings: Any,
    llm_settings: Any,
) -> bool:
    """Resolve the effective thinking-mode setting."""
    if db_settings is not None and hasattr(db_settings, "enable_thinking"):
        db_value = getattr(db_settings, "enable_thinking", None)
        if db_value is not None:
            return db_value
    return getattr(llm_settings, "enable_thinking", True)


def get_reasoning_effort(
    db_settings: Any,
    llm_settings: Any,
) -> str:
    """Resolve the effective GPT-OSS reasoning-effort setting."""
    allowed = {"low", "medium", "high"}

    if db_settings is not None and hasattr(db_settings, "reasoning_effort"):
        db_value = (
            str(getattr(db_settings, "reasoning_effort", "medium") or "medium")
            .strip()
            .lower()
        )
        if db_value in allowed:
            return db_value

    ui_value = (
        str(getattr(llm_settings, "reasoning_effort", "medium") or "medium")
        .strip()
        .lower()
    )
    if ui_value in allowed:
        return ui_value

    return "medium"


def get_gguf_runtime_params(
    chatbot: Any,
) -> dict[str, Any]:
    """Build llama.cpp generation kwargs from chatbot settings."""
    if not chatbot:
        return {}

    return {
        "max_tokens": getattr(chatbot, "max_new_tokens", 4096),
        "temperature": getattr(chatbot, "temperature", 700) / 10000.0,
        "top_p": getattr(chatbot, "top_p", 900) / 1000.0,
        "top_k": getattr(chatbot, "top_k", 20),
        "repeat_penalty": getattr(
            chatbot,
            "repetition_penalty",
            115,
        )
        / 100.0,
    }


def get_provider_runtime_params(
    chatbot: Any,
    max_tokens_override: int | None = None,
) -> dict[str, Any]:
    """Build API-provider generation kwargs from chatbot settings.

    *max_tokens_override*: when provided, use this value instead of the
    chatbot's ``max_new_tokens``.  This allows per-pipeline overrides
    (e.g. DIALOGUE 2048, KNOWLEDGE 1500) to flow through the factory.
    """
    if not chatbot:
        default_tokens = (
            max_tokens_override if max_tokens_override is not None else 500
        )
        return {
            "temperature": 0.7,
            "max_tokens": default_tokens,
        }

    return {
        "temperature": getattr(chatbot, "temperature", 700) / 10000.0,
        "max_tokens": (
            max_tokens_override
            if max_tokens_override is not None
            else getattr(chatbot, "max_new_tokens", 500)
        ),
    }


def build_provider_runtime_config(
    llm_settings: Any,
    chatbot: Any,
    max_tokens_override: int | None = None,
) -> ProviderRuntimeConfig:
    """Return the request-scoped provider selection for model creation.

    *max_tokens_override*: per-pipeline max_tokens value from the
    routing rule.  Passed through to ``get_provider_runtime_params``.
    """
    provider_params = get_provider_runtime_params(
        chatbot, max_tokens_override=max_tokens_override,
    )
    if getattr(llm_settings, "use_local_llm", True):
        return _local_provider_runtime(provider_params)
    if getattr(llm_settings, "use_openrouter", False):
        return _openrouter_provider_runtime(llm_settings, provider_params)
    if getattr(llm_settings, "use_ollama", False):
        return _ollama_provider_runtime(llm_settings, provider_params)
    if getattr(llm_settings, "use_openai", False):
        return _openai_provider_runtime(llm_settings, provider_params)
    if getattr(llm_settings, "use_deepinfra", False):
        return _deepinfra_provider_runtime(llm_settings, provider_params)
    return _local_provider_runtime(provider_params)


def _local_provider_runtime(
    provider_params: dict[str, Any],
) -> ProviderRuntimeConfig:
    """Build the local provider runtime configuration."""
    return ProviderRuntimeConfig(
        provider=ModelService.LOCAL.value,
        **provider_params
    )


def _openrouter_provider_runtime(
    llm_settings: Any,
    provider_params: dict[str, Any],
) -> ProviderRuntimeConfig:
    """Build the OpenRouter provider runtime configuration."""
    api_key = getattr(llm_settings, "openrouter_api_key", None) or os.getenv(
        "OPENROUTER_API_KEY"
    )
    return ProviderRuntimeConfig(
        provider=ModelService.OPENROUTER.value,
        model_name=getattr(
            llm_settings,
            "model",
            "mistralai/mistral-7b-instruct",
        ),
        api_key=api_key,
        **provider_params,
    )


def _ollama_provider_runtime(
    llm_settings: Any,
    provider_params: dict[str, Any],
) -> ProviderRuntimeConfig:
    """Build the Ollama provider runtime configuration."""
    return ProviderRuntimeConfig(
        provider=ModelService.OLLAMA.value,
        model_name=getattr(llm_settings, "ollama_model", "llama2"),
        base_url=getattr(
            llm_settings,
            "ollama_base_url",
            "http://localhost:11434",
        ),
        **provider_params,
    )


def _openai_provider_runtime(
    llm_settings: Any,
    provider_params: dict[str, Any],
) -> ProviderRuntimeConfig:
    """Build the OpenAI provider runtime configuration."""
    api_key = getattr(llm_settings, "openai_api_key", None) or os.getenv(
        "OPENAI_API_KEY"
    )
    return ProviderRuntimeConfig(
        provider=ModelService.OPENAI.value,
        model_name=getattr(llm_settings, "openai_model", "gpt-4"),
        api_key=api_key,
        **provider_params,
    )


def _deepinfra_provider_runtime(
    llm_settings: Any,
    provider_params: dict[str, Any],
) -> ProviderRuntimeConfig:
    """Build the DeepInfra provider runtime configuration."""
    api_key = getattr(llm_settings, "deepinfra_api_key", None) or os.getenv(
        "DEEPINFRA_API_KEY"
    )
    return ProviderRuntimeConfig(
        provider=ModelService.DEEPINFRA.value,
        model_name=getattr(
            llm_settings,
            "deepinfra_model",
            "mistralai/Mistral-Nemo-Instruct-2407",
        ),
        api_key=api_key,
        **provider_params,
    )


def build_local_runtime_config(
    db_settings: Any,
    llm_settings: Any,
    chatbot: Any,
) -> LocalRuntimeConfig:
    """Return the resolved persisted runtime config for local/GGUF loads."""
    return LocalRuntimeConfig(
        quantization_bits=get_quantization_bits(db_settings),
        enable_thinking=get_enable_thinking(db_settings, llm_settings),
        reasoning_effort=get_reasoning_effort(db_settings, llm_settings),
        gguf_params=get_gguf_runtime_params(chatbot),
    )
