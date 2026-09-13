"""Cloud provider-backed chat model creation helpers.

Delegates the actual model construction to the builder functions in
:mod:`airunner_services.cloud.llm.model_builders`.
"""

from __future__ import annotations

from typing import Callable

from langchain_core.language_models.chat_models import BaseChatModel

from airunner_services.llm.runtime_config import ProviderRuntimeConfig

from airunner_services.contract_enums import ModelService


def create_provider_model_from_runtime(
    provider_runtime: ProviderRuntimeConfig,
    create_openrouter_model: Callable[..., BaseChatModel],
    create_ollama_model: Callable[..., BaseChatModel],
    create_openai_model: Callable[..., BaseChatModel],
) -> BaseChatModel | None:
    """Create one non-local chat model from a provider runtime config."""
    if provider_runtime.provider == ModelService.OPENROUTER.value:
        return _create_openrouter_runtime(
            provider_runtime,
            create_openrouter_model,
        )
    if provider_runtime.provider == ModelService.DEEPINFRA.value:
        return _create_deepinfra_runtime(provider_runtime)
    if provider_runtime.provider == ModelService.OLLAMA.value:
        return _create_ollama_runtime(
            provider_runtime,
            create_ollama_model,
        )
    if provider_runtime.provider == ModelService.OPENAI.value:
        return _create_openai_runtime(
            provider_runtime,
            create_openai_model,
        )
    return None


def _create_deepinfra_runtime(
    provider_runtime: ProviderRuntimeConfig,
) -> BaseChatModel:
    """Create one DeepInfra-backed model from provider runtime config."""
    from airunner_services.cloud.llm.model_builders import (
        create_deepinfra_model,
    )

    api_key = _require_provider_api_key(
        provider_runtime.api_key,
        "DEEPINFRA_API_KEY environment variable required for DeepInfra",
    )
    return create_deepinfra_model(
        api_key=api_key,
        model_name=(
            provider_runtime.model_name
            or "mistralai/Mistral-Nemo-Instruct-2407"
        ),
        temperature=provider_runtime.temperature,
        max_tokens=provider_runtime.max_tokens,
    )


def _create_openrouter_runtime(
    provider_runtime: ProviderRuntimeConfig,
    create_openrouter_model: Callable[..., BaseChatModel],
) -> BaseChatModel:
    """Create one OpenRouter-backed model from provider runtime config."""
    api_key = _require_provider_api_key(
        provider_runtime.api_key,
        "OPENROUTER_API_KEY environment variable required for OpenRouter",
    )
    return create_openrouter_model(
        api_key=api_key,
        model_name=(
            provider_runtime.model_name or "mistralai/mistral-7b-instruct"
        ),
        temperature=provider_runtime.temperature,
        max_tokens=provider_runtime.max_tokens,
    )


def _create_ollama_runtime(
    provider_runtime: ProviderRuntimeConfig,
    create_ollama_model: Callable[..., BaseChatModel],
) -> BaseChatModel:
    """Create one Ollama-backed model from provider runtime config."""
    return create_ollama_model(
        model_name=provider_runtime.model_name or "llama2",
        base_url=(provider_runtime.base_url or "http://localhost:11434"),
        temperature=provider_runtime.temperature,
    )


def _create_openai_runtime(
    provider_runtime: ProviderRuntimeConfig,
    create_openai_model: Callable[..., BaseChatModel],
) -> BaseChatModel:
    """Create one OpenAI-backed model from provider runtime config."""
    api_key = _require_provider_api_key(
        provider_runtime.api_key,
        "OPENAI_API_KEY environment variable required for OpenAI",
    )
    return create_openai_model(
        api_key=api_key,
        model_name=provider_runtime.model_name or "gpt-4",
        temperature=provider_runtime.temperature,
        max_tokens=provider_runtime.max_tokens,
    )


def _require_provider_api_key(
    api_key: str | None,
    message: str,
) -> str:
    """Return one provider API key or raise a configuration error."""
    if api_key:
        return api_key
    raise ValueError(message)
