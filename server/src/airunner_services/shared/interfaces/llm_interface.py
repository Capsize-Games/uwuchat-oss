"""Common interface for LLM inference — satisfied by both edge and cloud."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Iterator


class LLMInferenceInterface(ABC):
    """Abstract inference boundary for LLM chat / text generation.

    Every LLM backend (local GGUF via llama.cpp, OpenRouter API, Ollama,
    OpenAI API) must satisfy this interface so the rest of the application
    never needs to know which backend is active.
    """

    @abstractmethod
    def generate(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """Non-streaming generation — return one complete response string.

        Args:
            messages: List of chat message dicts with ``role`` and
                ``content`` keys.
            **kwargs: Backend-specific tuning parameters (temperature,
                max_tokens, etc.).

        Returns:
            The complete assistant response text.
        """

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> Iterator[str]:
        """Streaming generation — yield response tokens as they arrive.

        Args:
            messages: List of chat message dicts with ``role`` and
                ``content`` keys.
            **kwargs: Backend-specific tuning parameters.

        Yields:
            Individual response tokens (strings).
        """

    @abstractmethod
    def cancel(self) -> None:
        """Cancel the current generation on a best-effort basis."""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Return whether the model / backend is ready for inference."""

    @abstractmethod
    def load_model(self) -> None:
        """Prepare the backend for inference (load weights, warm up, etc.)."""

    @abstractmethod
    def unload_model(self) -> None:
        """Release backend resources."""


class AsyncLLMInferenceInterface(ABC):
    """Async variant of :class:`LLMInferenceInterface` for integrations that
    require non-blocking I/O (e.g. async HTTP for cloud providers).
    """

    @abstractmethod
    async def generate_async(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        """Async non-streaming generation."""

    @abstractmethod
    async def stream_async(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Async streaming generation."""

    @abstractmethod
    async def cancel_async(self) -> None:
        """Async cancellation."""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Return whether the backend is ready."""

    @abstractmethod
    async def load_model_async(self) -> None:
        """Async model loading."""

    @abstractmethod
    async def unload_model_async(self) -> None:
        """Async resource release."""


__all__ = [
    "AsyncLLMInferenceInterface",
    "LLMInferenceInterface",
]
