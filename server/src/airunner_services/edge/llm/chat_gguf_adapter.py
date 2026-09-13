"""Adapter wrapping ChatGGUF behind the shared LLMInferenceInterface."""

from __future__ import annotations

from typing import Any, Iterator, Optional

from airunner_services.shared.interfaces.llm_interface import (
    LLMInferenceInterface,
)
from airunner_services.settings import AIRUNNER_MAX_TOKENS


class ChatGGUFAdapter(LLMInferenceInterface):
    """Bridge ChatGGUF (llama.cpp) into the shared LLM inference contract.

    This adapter performs lazy imports so the edge/ package can be
    imported without triggering a llama-cpp-python load until the adapter
    is actually used.
    """

    def __init__(
        self,
        model_path: str,
        *,
        n_ctx: int = AIRUNNER_MAX_TOKENS,
        n_gpu_layers: int = -1,
        n_batch: int = 256,
        max_tokens: int = AIRUNNER_MAX_TOKENS,
        temperature: float = 0.6,
        top_p: float = 0.95,
        top_k: int = 20,
        repeat_penalty: float = 1.15,
        flash_attn: bool = True,
        enable_thinking: bool = True,
        reasoning_effort: str = "medium",
        gguf_runtime_profile: Optional[str] = None,
    ) -> None:
        self._model_path = model_path
        self._n_ctx = n_ctx
        self._n_gpu_layers = n_gpu_layers
        self._n_batch = n_batch
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._top_p = top_p
        self._top_k = top_k
        self._repeat_penalty = repeat_penalty
        self._flash_attn = flash_attn
        self._enable_thinking = enable_thinking
        self._reasoning_effort = reasoning_effort
        self._gguf_runtime_profile = gguf_runtime_profile
        self._model: Any = None

    # ------------------------------------------------------------------
    # LLMInferenceInterface
    # ------------------------------------------------------------------

    def generate(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """Non-streaming generation — collect streamed output."""
        tokens: list[str] = []
        for token in self.stream(messages, **kwargs):
            tokens.append(token)
        return "".join(tokens)

    def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> Iterator[str]:
        """Stream tokens from the local GGUF model."""
        model = self._model or self._build_model()
        # Delegate to ChatGGUF's internal streaming.
        try:
            response = model._generate(
                messages=messages,
                stop=kwargs.get("stop"),
                run_manager=kwargs.get("run_manager"),
                **kwargs,
            )
            yield response.generations[0][0].text
        except Exception:
            raise

    def cancel(self) -> None:
        """Interrupt the current generation."""
        if self._model is not None:
            self._model._interrupted = True

    @property
    def is_loaded(self) -> bool:
        """Return whether the GGUF model is loaded."""
        return self._model is not None

    def load_model(self) -> None:
        """Load the GGUF model via llama.cpp."""
        self._build_model()

    def unload_model(self) -> None:
        """Release the llama.cpp model and free GPU memory."""
        if self._model is not None:
            try:
                self._model._llama.close()
            except Exception:
                pass
            self._model = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_model(self) -> Any:
        """Lazily create one ChatGGUF instance."""
        from airunner_services.edge.llm.chat_gguf import ChatGGUF

        self._model = ChatGGUF(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            n_gpu_layers=self._n_gpu_layers,
            n_batch=self._n_batch,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            top_p=self._top_p,
            top_k=self._top_k,
            repeat_penalty=self._repeat_penalty,
            flash_attn=self._flash_attn,
            enable_thinking=self._enable_thinking,
            reasoning_effort=self._reasoning_effort,
            gguf_runtime_profile=self._gguf_runtime_profile,
        )
        return self._model
