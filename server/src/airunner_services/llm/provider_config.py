"""Backward-compat LLMProviderConfig — data sourced from edge/cloud modules.

Data split:
  - LOCAL_MODELS, GGUF profiles, storage paths → edge.llm.providers
  - OPENROUTER_MODELS, OLLAMA_MODELS           → cloud.llm.providers

All class methods are kept here for backward compatibility since many
callers use ``LLMProviderConfig.get_model_info(...)`` etc.
"""

import os
from typing import Any, Dict, List, Optional

from airunner_services.cloud.llm.providers import (
    OLLAMA_MODELS as _OLLAMA_MODELS,
    OPENROUTER_MODELS as _OPENROUTER_MODELS,
)
from airunner_services.edge.llm.providers import (
    local_models as _local_models_fn,
    supported_local_model_ids as _supported_ids_fn,
)

from airunner_services.contract_enums import ModelService


class LLMProviderConfig:
    """Available models for each LLM provider.

    Data is sourced from the canonical edge/cloud provider modules.
    """

    LOCAL_MODELS: Dict[str, Dict[str, Any]] = _local_models_fn()
    OPENROUTER_MODELS: List[str] = list(_OPENROUTER_MODELS)
    OLLAMA_MODELS: List[str] = list(_OLLAMA_MODELS)
    _SUPPORTED_LOCAL_MODEL_IDS: tuple = _supported_ids_fn()

    @staticmethod
    def _normalize_identifier(identifier: str) -> str:
        return "".join(
            character
            for character in str(identifier or "").lower()
            if character.isalnum()
        )

    @classmethod
    def _iter_model_aliases(cls, model_info: Dict[str, Any]) -> List[str]:
        aliases = list(model_info.get("aliases", []))
        for key in ("name", "gguf_filename"):
            value = model_info.get(key)
            if value:
                aliases.append(str(value))
        return aliases

    @staticmethod
    def get_gguf_runtime_profile(
        provider: str,
        model_id: str,
        profile_name: str = "default",
    ) -> Dict[str, Any]:
        """Return one GGUF runtime profile for one local model."""
        model_info = LLMProviderConfig.get_model_info(provider, model_id) or {}
        profiles = model_info.get("gguf_runtime_profiles") or {}
        profile = profiles.get(profile_name) or {}
        if profile:
            return dict(profile)

        legacy_profile: Dict[str, Any] = {}
        default_n_ctx = model_info.get("gguf_default_n_ctx")
        if default_n_ctx:
            legacy_profile["n_ctx"] = int(default_n_ctx)
        default_n_batch = model_info.get("gguf_default_n_batch")
        if default_n_batch:
            legacy_profile["n_batch"] = int(default_n_batch)
        return legacy_profile

    @classmethod
    def get_models_for_provider(cls, provider: str) -> List[str]:
        if provider == ModelService.LOCAL.value:
            return [
                model_id
                for model_id in cls._SUPPORTED_LOCAL_MODEL_IDS
                if model_id in cls.LOCAL_MODELS
            ]
        if provider == ModelService.OPENROUTER.value:
            return cls.OPENROUTER_MODELS
        if provider == ModelService.OLLAMA.value:
            return cls.OLLAMA_MODELS
        return []

    @classmethod
    def get_model_display_name(cls, provider: str, model_id: str) -> str:
        if (
            provider == ModelService.LOCAL.value and
            model_id in cls.LOCAL_MODELS
        ):
            model_info = cls.LOCAL_MODELS[model_id]
            if model_info["function_calling"]:
                return f"{model_info['name']} ⚡"
            return f"{model_info['name']}"
        return model_id

    @classmethod
    def get_model_info(cls, provider: str, model_id: str) -> Dict:
        if provider == ModelService.LOCAL.value and model_id in cls.LOCAL_MODELS:
            return cls.LOCAL_MODELS[model_id]
        return {}

    @classmethod
    def get_model_id_for_name(cls, provider: str, model_name: str) -> str:
        target = cls._normalize_identifier(model_name)
        if provider != ModelService.LOCAL.value or not target:
            return ""

        for model_id, model_info in cls.LOCAL_MODELS.items():
            for alias in cls._iter_model_aliases(model_info):
                if cls._normalize_identifier(alias) == target:
                    return model_id
        return ""

    @classmethod
    def resolve_model_id(cls, provider: str, identifier: str) -> str:
        if provider != ModelService.LOCAL.value or not identifier:
            return ""

        normalized = cls._normalize_identifier(identifier)
        for model_id in cls.LOCAL_MODELS:
            if cls._normalize_identifier(model_id) == normalized:
                return model_id

        model_id = cls.get_model_id_for_name(provider, identifier)
        if model_id:
            return model_id

        return cls.get_model_id_for_repo_id(provider, identifier)

    @classmethod
    def get_model_id_for_repo_id(cls, provider: str, repo_id: str) -> str:
        if provider != ModelService.LOCAL.value or not repo_id:
            return ""

        target = str(repo_id).strip().lower()

        for model_id, model_info in cls.LOCAL_MODELS.items():
            candidates = {
                str(model_info.get("repo_id", "")).lower(),
                str(model_info.get("gguf_repo_id", "")).lower(),
            }
            if target in candidates:
                return model_id
        return ""

    @classmethod
    def resolve_download_target(
        cls,
        provider: str,
        model_id: Optional[str] = None,
        repo_id: Optional[str] = None,
        prefer_pre_quantized: bool = True,
    ) -> Optional[Dict[str, Any]]:
        if provider != ModelService.LOCAL.value:
            return None

        resolved_model_id = model_id or cls.get_model_id_for_repo_id(
            provider,
            repo_id or "",
        )
        if not resolved_model_id:
            return None

        model_info = cls.get_model_info(provider, resolved_model_id)
        if not model_info:
            return None

        if prefer_pre_quantized:
            gguf_info = cls.get_gguf_info(provider, resolved_model_id)
            if gguf_info:
                return {
                    "model_id": resolved_model_id,
                    "model_name": model_info.get("name", resolved_model_id),
                    "repo_id": gguf_info["repo_id"],
                    "model_type": "gguf",
                    "gguf_filename": gguf_info["filename"],
                    "quantization_bits": 0,
                }

        return {
            "model_id": resolved_model_id,
            "model_name": model_info.get("name", resolved_model_id),
            "repo_id": model_info.get("repo_id", repo_id or ""),
            "model_type": model_info.get("model_type", "llm"),
            "gguf_filename": None,
            "quantization_bits": None,
        }

    @staticmethod
    def _get_repo_owner(repo_id: str) -> str:
        if not repo_id:
            return ""
        return str(repo_id).split("/", 1)[0].strip()

    @classmethod
    def get_local_storage_path(
        cls,
        base_path: str,
        provider: str,
        model_id: Optional[str] = None,
        repo_id: Optional[str] = None,
        prefer_pre_quantized: bool = True,
    ) -> str:
        base_dir = os.path.join(
            os.path.expanduser(base_path),
            "text/models/llm/causallm",
        )
        resolved = cls.resolve_download_target(
            provider,
            model_id=model_id,
            repo_id=repo_id,
            prefer_pre_quantized=prefer_pre_quantized,
        )
        if not resolved:
            fallback = str(model_id or repo_id or "model")
            return os.path.join(base_dir, fallback.split("/")[-1] or "model")

        if resolved.get("model_type") == "gguf":
            resolved_model_id = str(resolved.get("model_id", ""))
            model_info = cls.get_model_info(provider, resolved_model_id)
            storage_subdir = str(
                model_info.get("local_storage_subdir", "")
            ).strip()
            if storage_subdir:
                return os.path.join(base_dir, storage_subdir)

            repo_owner = cls._get_repo_owner(resolved.get("repo_id", ""))
            if repo_owner:
                return os.path.join(base_dir, repo_owner)

        return os.path.join(
            base_dir,
            resolved.get("model_name", model_id or "model"),
        )

    @classmethod
    def get_expected_local_artifact_path(
        cls,
        base_path: str,
        provider: str,
        model_id: Optional[str] = None,
        repo_id: Optional[str] = None,
        prefer_pre_quantized: bool = True,
    ) -> str:
        storage_path = cls.get_local_storage_path(
            base_path,
            provider,
            model_id=model_id,
            repo_id=repo_id,
            prefer_pre_quantized=prefer_pre_quantized,
        )
        resolved = cls.resolve_download_target(
            provider,
            model_id=model_id,
            repo_id=repo_id,
            prefer_pre_quantized=prefer_pre_quantized,
        )
        if resolved and resolved.get("model_type") == "gguf":
            gguf_filename = resolved.get("gguf_filename")
            if gguf_filename:
                return os.path.join(storage_path, gguf_filename)
        return storage_path

    @classmethod
    def get_vram_for_quantization(
        cls,
        provider: str,
        model_id: str,
        quantization_bits: int,
    ) -> int:
        if provider == ModelService.LOCAL.value and model_id in cls.LOCAL_MODELS:
            model_info = cls.LOCAL_MODELS[model_id]
            vram_key = f"vram_{quantization_bits}bit_gb"
            return model_info.get(vram_key, 0)
        return 0

    @classmethod
    def requires_download(cls, provider: str, model_id: str) -> bool:
        return provider == ModelService.LOCAL.value and model_id != "custom"

    @classmethod
    def has_gguf_support(cls, provider: str, model_id: str) -> bool:
        if provider == ModelService.LOCAL.value and model_id in cls.LOCAL_MODELS:
            model_info = cls.LOCAL_MODELS[model_id]
            return bool(
                model_info.get("gguf_repo_id")
                and model_info.get("gguf_filename")
            )
        return False

    @classmethod
    def has_gguf_variant(cls, model_id: str) -> bool:
        if model_id in cls.LOCAL_MODELS:
            model_info = cls.LOCAL_MODELS[model_id]
            return bool(
                model_info.get("gguf_repo_id")
                and model_info.get("gguf_filename")
            )
        return False

    @classmethod
    def get_gguf_info(
        cls,
        provider: str,
        model_id: str,
    ) -> Optional[Dict[str, str]]:
        if provider == ModelService.LOCAL.value and model_id in cls.LOCAL_MODELS:
            model_info = cls.LOCAL_MODELS[model_id]
            repo_id = model_info.get("gguf_repo_id")
            filename = model_info.get("gguf_filename")
            if repo_id and filename:
                return {
                    "repo_id": repo_id,
                    "filename": filename,
                }
        return None


__all__ = ["LLMProviderConfig"]
