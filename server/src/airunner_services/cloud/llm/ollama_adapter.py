"""Ollama adapter implementing the shared LLMInferenceInterface."""

from __future__ import annotations

from typing import Any, Iterator

from airunner_services.shared.interfaces.llm_interface import (
    LLMInferenceInterface,
)


class OllamaAdapter(LLMInferenceInterface):
    """LLM inference via a local or remote Ollama server.

    Uses LangChain's ``ChatOllama``. Requires a running Ollama instance
    (default ``http://localhost:11434``).
    """

    def __init__(
        self,
        model_name: str = "llama3.2",
        *,
        base_url: str = "http://localhost:11434",
        temperature: float = 0.7,
    ) -> None:
        self._model_name = model_name
        self._base_url = base_url
        self._temperature = temperature
        self._model: Any = None
        self._cancelled = False

    # ------------------------------------------------------------------
    # LLMInferenceInterface
    # ------------------------------------------------------------------

    def generate(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        model = self._model or self._build_model()
        response = model.invoke(messages, **kwargs)
        return str(response.content)

    def stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> Iterator[str]:
        model = self._model or self._build_model()
        self._cancelled = False
        for chunk in model.stream(messages, **kwargs):
            if self._cancelled:
                break
            content = getattr(chunk, "content", None)
            if content:
                yield str(content)

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_loaded(self) -> bool:
        return True  # Ollama is an always-available API

    def load_model(self) -> None:
        self._build_model()

    def unload_model(self) -> None:
        self._model = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_model(self) -> Any:
        from airunner_services.cloud.llm.model_builders import (
            create_ollama_model,
        )

        self._model = create_ollama_model(
            model_name=self._model_name,
            base_url=self._base_url,
            temperature=self._temperature,
        )
        return self._model
