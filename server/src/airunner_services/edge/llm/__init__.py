"""Edge LLM package — local GGUF inference via llama.cpp."""

from __future__ import annotations

from airunner_services.edge.llm.chat_gguf_adapter import ChatGGUFAdapter
from airunner_services.edge.llm.providers import (
    get_gguf_info,
    get_gguf_runtime_profile,
    get_local_storage_path,
    get_model_display_name,
    get_model_info,
    get_models_for_provider,
    get_vram_for_quantization,
    has_gguf_support,
    local_models,
    requires_download,
    resolve_download_target,
    resolve_model_id,
    supported_local_model_ids,
)

__all__ = [
    "ChatGGUFAdapter",
    "get_gguf_info",
    "get_gguf_runtime_profile",
    "get_local_storage_path",
    "get_model_display_name",
    "get_model_info",
    "get_models_for_provider",
    "get_vram_for_quantization",
    "has_gguf_support",
    "local_models",
    "requires_download",
    "resolve_download_target",
    "resolve_model_id",
    "supported_local_model_ids",
]
