"""Edge-local LLM provider configuration and model metadata.

This module contains the model definitions, runtime profiles, download
targets, and storage-path logic for local GGUF models. It is the
edge counterpart of :mod:`airunner_services.cloud.llm.providers`.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from airunner_services.settings import AIRUNNER_MAX_TOKENS

# ------------------------------------------------------------------
# Local model registry
# ------------------------------------------------------------------

_LOCAL_MODELS: Dict[str, Dict[str, Any]] = {
    "qwen3.5-9b": {
        "name": "Qwen3.5-9B",
        "repo_id": "Qwen/Qwen3.5-9B",
        "model_type": "llm",
        "function_calling": True,
        "tool_calling_mode": "json",
        "supports_thinking": True,
        "rag_capable": True,
        "vision_capable": False,
        "code_capable": True,
        "context_length": 262144,
        "native_context_length": 262144,
        "yarn_max_context_length": 262144,
        "supports_yarn": False,
        "vram_2bit_gb": 6,
        "vram_4bit_gb": 10,
        "vram_8bit_gb": 12,
        "description": (
            "Qwen3.5 9B long-context local GGUF model for "
            "conversation and analysis"
        ),
        "gguf_repo_id": "unsloth/Qwen3.5-9B-GGUF",
        "gguf_filename": "Qwen3.5-9B-Q8_0.gguf",
        "local_storage_subdir": "Qwen",
        "aliases": [
            "Qwen 3.5 9B",
            "Qwen3.5 9B",
            "Qwen3.5-9B-Q8_0.gguf",
        ],
        "gguf_runtime_profiles": {
            "default": {"n_ctx": AIRUNNER_MAX_TOKENS, "n_batch": 256},
            "combined_tts": {
                "n_ctx": 4096,
                "n_gpu_layers": 10,
                "n_batch": 256,
            },
        },
    },
    "gpt-oss-20b": {
        "name": "GPT-OSS 20B",
        "repo_id": "openai/gpt-oss-20b",
        "model_type": "llm",
        "function_calling": False,
        "tool_calling_mode": "react",
        "supports_thinking": False,
        "supports_reasoning_effort": True,
        "rag_capable": True,
        "vision_capable": False,
        "code_capable": True,
        "context_length": 131072,
        "native_context_length": 4096,
        "yarn_max_context_length": 131072,
        "supports_yarn": True,
        "vram_2bit_gb": 10,
        "vram_4bit_gb": 14,
        "vram_8bit_gb": 20,
        "description": (
            "GPT-OSS 20B GGUF for local llama.cpp code and reasoning "
            "workloads"
        ),
        "gguf_repo_id": "unsloth/gpt-oss-20b-GGUF",
        "gguf_filename": "gpt-oss-20b-F16.gguf",
        "gguf_default_n_ctx": 8192,
        "gguf_default_n_batch": 256,
        "local_storage_subdir": "gpt_oss",
        "aliases": [
            "GPT-OSS",
            "GPT OSS",
            "gpt_oss",
            "gpt-oss-20b-F16.gguf",
        ],
        "gguf_runtime_profiles": {
            "default": {"n_ctx": 8192, "n_batch": 256},
            "combined_tts": {
                "n_ctx": 4096,
                "n_gpu_layers": 0,
                "n_batch": 256,
            },
        },
    },
    "custom": {
        "name": "Custom Local Path",
        "repo_id": "",
        "model_type": "llm",
        "function_calling": False,
        "tool_calling_mode": "react",
        "supports_thinking": False,
        "rag_capable": True,
        "vision_capable": False,
        "code_capable": False,
        "context_length": 0,
        "vram_2bit_gb": 0,
        "vram_4bit_gb": 0,
        "vram_8bit_gb": 0,
        "description": (
            "Use custom model path (auto-detects tool calling mode)"
        ),
    },
}

_SUPPORTED_LOCAL_MODEL_IDS = ("qwen3.5-9b", "gpt-oss-20b", "custom")


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def local_models() -> Dict[str, Dict[str, Any]]:
    """Return a shallow copy of the local-model registry."""
    return dict(_LOCAL_MODELS)


def supported_local_model_ids() -> tuple[str, ...]:
    """Return the set of known local model identifiers."""
    return _SUPPORTED_LOCAL_MODEL_IDS


def get_model_info(model_id: str) -> Dict[str, Any]:
    """Return metadata for one local model, or an empty dict."""
    return dict(_LOCAL_MODELS.get(model_id, {}))


def get_gguf_runtime_profile(
    model_id: str,
    profile_name: str = "default",
) -> Dict[str, Any]:
    """Return one GGUF runtime profile for one local model."""
    model_info = _LOCAL_MODELS.get(model_id, {})
    profiles = model_info.get("gguf_runtime_profiles") or {}
    profile = profiles.get(profile_name) or {}
    if profile:
        return dict(profile)
    legacy: Dict[str, Any] = {}
    default_n_ctx = model_info.get("gguf_default_n_ctx")
    if default_n_ctx:
        legacy["n_ctx"] = int(default_n_ctx)
    default_n_batch = model_info.get("gguf_default_n_batch")
    if default_n_batch:
        legacy["n_batch"] = int(default_n_batch)
    return legacy


def get_models_for_provider() -> List[str]:
    """Return the list of supported local model IDs."""
    return [mid for mid in _SUPPORTED_LOCAL_MODEL_IDS if mid in _LOCAL_MODELS]


def get_model_display_name(model_id: str) -> str:
    """Return a human-readable display name for one local model."""
    info = _LOCAL_MODELS.get(model_id, {})
    name = info.get("name", model_id)
    if info.get("function_calling"):
        return f"{name} ⚡"
    return str(name)


def get_model_id_for_name(model_name: str) -> str:
    """Resolve one model display-name or alias to a canonical ID."""
    target = _normalize_identifier(model_name)
    if not target:
        return ""
    for model_id, info in _LOCAL_MODELS.items():
        for alias in _iter_model_aliases(info):
            if _normalize_identifier(alias) == target:
                return model_id
    return ""


def resolve_model_id(identifier: str) -> str:
    """Resolve any identifier (ID, alias, repo_id) to a canonical ID."""
    if not identifier:
        return ""
    normalized = _normalize_identifier(identifier)
    for model_id in _LOCAL_MODELS:
        if _normalize_identifier(model_id) == normalized:
            return model_id
    by_name = get_model_id_for_name(identifier)
    if by_name:
        return by_name
    return get_model_id_for_repo_id(identifier)


def get_model_id_for_repo_id(repo_id: str) -> str:
    """Find a local model matching one HuggingFace repo ID."""
    if not repo_id:
        return ""
    target = str(repo_id).strip().lower()
    for model_id, info in _LOCAL_MODELS.items():
        candidates = {
            str(info.get("repo_id", "")).lower(),
            str(info.get("gguf_repo_id", "")).lower(),
        }
        if target in candidates:
            return model_id
    return ""


def resolve_download_target(
    model_id: Optional[str] = None,
    repo_id: Optional[str] = None,
    prefer_pre_quantized: bool = True,
) -> Optional[Dict[str, Any]]:
    """Return download metadata for one local model."""
    resolved_id = model_id or get_model_id_for_repo_id(repo_id or "")
    if not resolved_id:
        return None
    info = get_model_info(resolved_id)
    if not info:
        return None
    if prefer_pre_quantized:
        gguf_info = get_gguf_info(resolved_id)
        if gguf_info:
            return {
                "model_id": resolved_id,
                "model_name": info.get("name", resolved_id),
                "repo_id": gguf_info["repo_id"],
                "model_type": "gguf",
                "gguf_filename": gguf_info["filename"],
                "quantization_bits": 0,
            }
    return {
        "model_id": resolved_id,
        "model_name": info.get("name", resolved_id),
        "repo_id": info.get("repo_id", repo_id or ""),
        "model_type": info.get("model_type", "llm"),
        "gguf_filename": None,
        "quantization_bits": None,
    }


def get_local_storage_path(
    base_path: str,
    model_id: Optional[str] = None,
    repo_id: Optional[str] = None,
    prefer_pre_quantized: bool = True,
) -> str:
    """Return the local filesystem path for one model storage directory."""
    base_dir = os.path.join(
        os.path.expanduser(base_path),
        "text/models/llm/causallm",
    )
    resolved = resolve_download_target(
        model_id=model_id,
        repo_id=repo_id,
        prefer_pre_quantized=prefer_pre_quantized,
    )
    if not resolved:
        fallback = str(model_id or repo_id or "model")
        return os.path.join(base_dir, fallback.split("/")[-1] or "model")
    if resolved.get("model_type") == "gguf":
        resolved_id = str(resolved.get("model_id", ""))
        info = get_model_info(resolved_id)
        storage_subdir = str(info.get("local_storage_subdir", "")).strip()
        if storage_subdir:
            return os.path.join(base_dir, storage_subdir)
        repo_owner = _get_repo_owner(resolved.get("repo_id", ""))
        if repo_owner:
            return os.path.join(base_dir, repo_owner)
    return os.path.join(
        base_dir,
        resolved.get("model_name", model_id or "model"),
    )


def get_expected_local_artifact_path(
    base_path: str,
    model_id: Optional[str] = None,
    repo_id: Optional[str] = None,
    prefer_pre_quantized: bool = True,
) -> str:
    """Return the path to the actual model file (e.g. GGUF file)."""
    storage = get_local_storage_path(
        base_path,
        model_id=model_id,
        repo_id=repo_id,
        prefer_pre_quantized=prefer_pre_quantized,
    )
    resolved = resolve_download_target(
        model_id=model_id,
        repo_id=repo_id,
        prefer_pre_quantized=prefer_pre_quantized,
    )
    if resolved and resolved.get("model_type") == "gguf":
        gguf_name = resolved.get("gguf_filename")
        if gguf_name:
            return os.path.join(storage, gguf_name)
    return storage


def get_vram_for_quantization(model_id: str, quantization_bits: int) -> int:
    """Return the estimated VRAM (GB) for one quantized local model."""
    info = _LOCAL_MODELS.get(model_id, {})
    vram_key = f"vram_{quantization_bits}bit_gb"
    return info.get(vram_key, 0)


def requires_download(model_id: str) -> bool:
    """Return True when the model must be downloaded before use."""
    return model_id != "custom"


def has_gguf_support(model_id: str) -> bool:
    """Return True when the model has a pre-quantized GGUF variant."""
    info = _LOCAL_MODELS.get(model_id, {})
    return bool(info.get("gguf_repo_id") and info.get("gguf_filename"))


def get_gguf_info(model_id: str) -> Optional[Dict[str, str]]:
    """Return GGUF repo/filename when available for one local model."""
    info = _LOCAL_MODELS.get(model_id, {})
    repo_id = info.get("gguf_repo_id")
    filename = info.get("gguf_filename")
    if repo_id and filename:
        return {"repo_id": repo_id, "filename": filename}
    return None


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _normalize_identifier(identifier: str) -> str:
    return "".join(c for c in str(identifier or "").lower() if c.isalnum())


def _iter_model_aliases(model_info: Dict[str, Any]) -> List[str]:
    aliases = list(model_info.get("aliases", []))
    for key in ("name", "gguf_filename"):
        value = model_info.get(key)
        if value:
            aliases.append(str(value))
    return aliases


def _get_repo_owner(repo_id: str) -> str:
    if not repo_id:
        return ""
    return str(repo_id).split("/", 1)[0].strip()
