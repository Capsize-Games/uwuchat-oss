"""Inference factory — selects edge or cloud adapters based on settings.

This factory replaces the existing :class:`ChatModelFactory` and extends
the same pattern to Art, TTS, and STT.
"""

from __future__ import annotations

from typing import Any

from airunner_services.contract_enums import ModelService
from airunner_services.shared.interfaces.art_interface import (
    ArtInferenceInterface,
)
from airunner_services.shared.interfaces.llm_interface import (
    LLMInferenceInterface,
)
from airunner_services.shared.interfaces.stt_interface import (
    STTInferenceInterface,
)
from airunner_services.shared.interfaces.tts_interface import (
    TTSInferenceInterface,
)


class InferenceFactory:
    """Create inference adapters based on persisted ``ModelService`` settings.

    Usage::

        factory = InferenceFactory.from_settings()
        llm = factory.create_llm()
        result = llm.generate([{"role": "user", "content": "Hello"}])
    """

    def __init__(self, model_service: str = ModelService.LOCAL.value) -> None:
        self._model_service = model_service

    # ------------------------------------------------------------------
    # Public factory methods
    # ------------------------------------------------------------------

    def create_llm(self, **kwargs: Any) -> LLMInferenceInterface:
        """Return the appropriate LLM adapter for the active provider."""
        provider = self._model_service
        if provider == ModelService.OPENROUTER.value:
            return self._openrouter_adapter(kwargs)
        if provider == ModelService.OLLAMA.value:
            return self._ollama_adapter(kwargs)
        if provider == ModelService.OPENAI.value:
            return self._openai_adapter(kwargs)
        return self._local_llm_adapter(kwargs)

    def create_art(
        self, timeout_seconds: float = 300.0
    ) -> ArtInferenceInterface:
        """Return the local art generation adapter (currently edge-only)."""
        return self._local_art_adapter(timeout_seconds)

    def create_stt(self) -> STTInferenceInterface:
        """Return the STT adapter (currently edge-only)."""
        return self._local_stt_adapter()

    def create_tts(self, engine: str = "openvoice") -> TTSInferenceInterface:
        """Return the TTS adapter for the requested engine."""
        return self._local_tts_adapter(engine)

    # ------------------------------------------------------------------
    # LLM adapters
    # ------------------------------------------------------------------

    @staticmethod
    def _local_llm_adapter(kwargs: dict[str, Any]) -> LLMInferenceInterface:
        from airunner_services.edge.llm.chat_gguf_adapter import (
            ChatGGUFAdapter,
        )

        model_path = kwargs.pop(
            "model_path",
            kwargs.pop("model", ""),
        )
        return ChatGGUFAdapter(model_path=model_path, **kwargs)

    @staticmethod
    def _openrouter_adapter(
        kwargs: dict[str, Any],
    ) -> LLMInferenceInterface:
        from airunner_services.cloud.llm.openrouter_adapter import (
            OpenRouterAdapter,
        )

        return OpenRouterAdapter(
            model_name=kwargs.pop(
                "model_name", "mistralai/mistral-7b-instruct"
            ),
            **kwargs,
        )

    @staticmethod
    def _ollama_adapter(kwargs: dict[str, Any]) -> LLMInferenceInterface:
        from airunner_services.cloud.llm.ollama_adapter import (
            OllamaAdapter,
        )

        return OllamaAdapter(
            model_name=kwargs.pop("model_name", "llama3.2"),
            **kwargs,
        )

    @staticmethod
    def _openai_adapter(kwargs: dict[str, Any]) -> LLMInferenceInterface:
        from airunner_services.cloud.llm.openai_adapter import (
            OpenAIAdapter,
        )

        return OpenAIAdapter(
            model_name=kwargs.pop("model_name", "gpt-4"),
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Art adapters
    # ------------------------------------------------------------------

    @staticmethod
    def _local_art_adapter(timeout_seconds: float) -> ArtInferenceInterface:
        from airunner_services.edge.art.art_generation_adapter import (
            ArtGenerationAdapter,
        )

        return ArtGenerationAdapter(timeout_seconds=timeout_seconds)

    # ------------------------------------------------------------------
    # STT adapters
    # ------------------------------------------------------------------

    @staticmethod
    def _local_stt_adapter() -> STTInferenceInterface:
        from airunner_services.edge.stt.faster_whisper_adapter import (
            FasterWhisperAdapter,
        )

        return FasterWhisperAdapter()

    # ------------------------------------------------------------------
    # TTS adapters
    # ------------------------------------------------------------------

    @staticmethod
    def _local_tts_adapter(engine: str) -> TTSInferenceInterface:
        if engine == "espeak":
            from airunner_services.edge.tts.espeak_adapter import (
                EspeakAdapter,
            )

            return EspeakAdapter()
        from airunner_services.edge.tts.openvoice_adapter import (
            OpenVoiceAdapter,
        )

        return OpenVoiceAdapter()

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_settings(
        cls,
        settings: Any | None = None,
    ) -> InferenceFactory:
        """Build a factory from persisted or provided settings."""
        model_service = ModelService.LOCAL.value
        if settings is not None:
            model_service = getattr(
                settings,
                "model_service",
                ModelService.LOCAL.value,
            )
        else:
            try:
                from airunner_services.database.models.llm_generator_settings import (
                    LLMGeneratorSettings,
                )

                row = LLMGeneratorSettings.objects.first()
                if row is not None:
                    model_service = getattr(
                        row,
                        "model_service",
                        ModelService.LOCAL.value,
                    )
            except Exception:
                pass
        return cls(model_service=model_service)
