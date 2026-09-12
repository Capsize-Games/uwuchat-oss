"""OpenRouter API adapter implementing the shared LLMInferenceInterface.

When the primary model returns an empty response (safety filter), the
stream falls back to a backup model that doesn't apply censorship.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from airunner_services.shared.interfaces.llm_interface import (
    LLMInferenceInterface,
)

from airunner_services.conf.model_settings import META_LLAMA_INSTRUCT_MODEL

_logger = logging.getLogger(__name__)

# Model used when the primary returns empty (Anthropic safety filter).
_FALLBACK_MODEL = META_LLAMA_INSTRUCT_MODEL


class OpenRouterAdapter(LLMInferenceInterface):
    """LLM inference via the OpenRouter API.

    Uses LangChain's ``ChatOpenAI`` pointed at the OpenRouter base URL.
    Requires ``OPENROUTER_API_KEY`` environment variable.
    """

    def __init__(
        self,
        model_name: str = "mistralai/mistral-7b-instruct",
        *,
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> None:
        import os

        self._model_name = model_name
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
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
        yielded = False
        for chunk in model.stream(messages, **kwargs):
            if self._cancelled:
                break
            content = getattr(chunk, "content", None)
            if content:
                yielded = True
                yield str(content)

        # If the primary model returned nothing (Anthropic safety filter),
        # retry with an uncensored backup model.
        if not yielded and not self._cancelled:
            _logger.info(
                "Primary model %s returned empty — retrying with %s",
                self._model_name, _FALLBACK_MODEL,
            )
            try:
                from airunner_services.cloud.llm.model_builders import (
                    create_openrouter_model,
                )
                fallback = create_openrouter_model(
                    api_key=self._api_key,
                    model_name=_FALLBACK_MODEL,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                )
                for chunk in fallback.stream(messages, **kwargs):
                    if self._cancelled:
                        break
                    content = getattr(chunk, "content", None)
                    if content:
                        yield str(content)
            except Exception as exc:
                _logger.warning("Fallback model also failed: %s", exc)

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
            create_openrouter_model,
        )

        self._model = create_openrouter_model(
            api_key=self._api_key,
            model_name=self._model_name,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        return self._model
