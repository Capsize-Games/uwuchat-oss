"""Shared runtime config dataclasses for LLM model creation.

These dataclasses are used by both cloud and edge/adapters modules.
They live here in a neutral location to avoid circular imports between
the ``cloud.llm`` and ``llm.adapters`` packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LocalRuntimeConfig:
    """Resolved persisted runtime settings for local chat-model creation."""

    quantization_bits: int
    enable_thinking: bool
    reasoning_effort: str
    gguf_params: dict[str, Any]


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    """Resolved request-scoped provider selection for one chat model."""

    provider: str
    model_name: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.7
    max_tokens: int = 500
