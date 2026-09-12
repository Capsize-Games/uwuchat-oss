"""Edge-local GGUF model builder — cloud builders live in cloud.llm."""

from __future__ import annotations

from typing import Optional

from airunner_services.edge.llm.chat_gguf import ChatGGUF
from airunner_services.edge.llm.chat_gguf_model_discovery import (
    find_gguf_file,
)

# Re-export cloud model builders from their canonical location.
from airunner_services.settings import AIRUNNER_MAX_TOKENS

_DEFAULT_GGUF_MODEL_KWARGS: dict[str, object] = {
    "gguf_runtime_profile": None,
    "n_ctx": AIRUNNER_MAX_TOKENS,
    "n_gpu_layers": -1,
    "n_batch": 256,
    "max_tokens": AIRUNNER_MAX_TOKENS,
    "temperature": 0.6,
    "top_p": 0.95,
    "top_k": 20,
    "repeat_penalty": 1.15,
    "flash_attn": True,
    "enable_thinking": True,
    "reasoning_effort": "medium",
    "tool_calling_mode": "native",
    "chat_format": None,
    "use_yarn": False,
    "yarn_orig_ctx": AIRUNNER_MAX_TOKENS,
    "preferred_filename": None,
}


def _resolved_gguf_file(
    model_path: str,
    preferred_filename: Optional[str],
) -> str:
    """Return one resolved GGUF file path or raise when missing."""
    gguf_file = (
        find_gguf_file(
            model_path,
            preferred_filename=preferred_filename,
        )
        if not model_path.endswith(".gguf")
        else model_path
    )
    if gguf_file:
        return gguf_file
    raise ValueError(f"No GGUF file found in {model_path}")


def _gguf_model_kwargs(
    gguf_file: str,
    **kwargs: object,
) -> dict[str, object]:
    """Return GGUF model constructor kwargs."""
    kwargs["model_path"] = gguf_file
    return kwargs


def create_gguf_model(model_path: str, **kwargs: object) -> ChatGGUF:
    """Create one GGUF-backed chat model."""
    resolved_kwargs = dict(_DEFAULT_GGUF_MODEL_KWARGS)
    resolved_kwargs.update(kwargs)
    preferred_filename = resolved_kwargs.pop("preferred_filename")
    gguf_file = _resolved_gguf_file(model_path, preferred_filename)
    return ChatGGUF(**_gguf_model_kwargs(gguf_file, **resolved_kwargs))
