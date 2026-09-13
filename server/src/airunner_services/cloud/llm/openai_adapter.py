"""OpenAI API adapter implementing the shared LLMInferenceInterface."""

from __future__ import annotations

from typing import Any, Iterator

from airunner_services.shared.interfaces.llm_interface import (
    LLMInferenceInterface,
)


class OpenAIAdapter(LLMInferenceInterface):
    """LLM inference via the OpenAI API.

    Uses LangChain's ``ChatOpenAI``. Requires ``OPENAI_API_KEY``
    environment variable.
    """

    def __init__(
        self,
        model_name: str = "gpt-4",
        *,
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> None:
        import os

        self._model_name = model_name
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._temperature = temperature
        self._max_tokens = max_tokens
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
        return True  # API backends are always "loaded"

    def load_model(self) -> None:
        self._build_model()

    def unload_model(self) -> None:
        self._model = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_model(self) -> Any:
        from airunner_services.cloud.llm.model_builders import (
            create_openai_model,
        )

        self._model = create_openai_model(
            api_key=self._api_key,
            model_name=self._model_name,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        return self._model
