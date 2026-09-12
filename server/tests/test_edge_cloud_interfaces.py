"""Validate the edge/cloud module split — interfaces, moved files, factory."""

from __future__ import annotations

from airunner_services.contract_enums import ModelService
from airunner_services.shared.factory import InferenceFactory


class TestSharedInterfaces:
    """Contract tests for shared inference interfaces."""

    def test_llm_interface(self) -> None:
        from airunner_services.shared.interfaces.llm_interface import (
            LLMInferenceInterface,
        )

        assert hasattr(LLMInferenceInterface, "generate")

    def test_art_interface(self) -> None:
        from airunner_services.shared.interfaces.art_interface import (
            ArtGenerationRequest,
            ArtInferenceInterface,
        )

        req = ArtGenerationRequest(prompt="a cat")
        assert req.prompt == "a cat"
        assert hasattr(ArtInferenceInterface, "generate")

    def test_tts_interface(self) -> None:
        from airunner_services.shared.interfaces.tts_interface import (
            TTSInferenceInterface,
        )

        assert hasattr(TTSInferenceInterface, "synthesize")

    def test_stt_interface(self) -> None:
        from airunner_services.shared.interfaces.stt_interface import (
            STTInferenceInterface,
        )

        assert hasattr(STTInferenceInterface, "transcribe")


class TestFactory:
    """Factory selection tests."""

    def test_factory_defaults_to_local(self) -> None:
        factory = InferenceFactory()
        assert factory._model_service == ModelService.LOCAL.value

    def test_factory_all_services(self) -> None:
        for service in ModelService:
            factory = InferenceFactory(model_service=service.value)
            assert factory._model_service == service.value


class TestEdgeLLM:
    """Verify chat_gguf files moved to edge/llm/."""

    def test_chat_gguf_importable(self) -> None:
        from airunner_services.edge.llm.chat_gguf import ChatGGUF

        assert ChatGGUF is not None

    def test_adapter_importable(self) -> None:
        from airunner_services.edge.llm.chat_gguf_adapter import (
            ChatGGUFAdapter,
        )
        from airunner_services.shared.interfaces.llm_interface import (
            LLMInferenceInterface,
        )

        assert issubclass(ChatGGUFAdapter, LLMInferenceInterface)

    def test_providers_importable(self) -> None:
        from airunner_services.edge.llm.providers import (
            get_model_info,
            local_models,
        )

        assert callable(get_model_info)
        assert isinstance(local_models(), dict)


class TestEdgeTTS:
    """Verify TTS files moved to edge/tts/."""

    def test_espeak_manager_importable(self) -> None:
        from airunner_services.edge.tts.espeak_model_manager import (
            EspeakModelManager,
        )

        assert EspeakModelManager is not None

    def test_openvoice_manager_importable(self) -> None:
        from airunner_services.edge.tts.openvoice_model_manager import (
            OpenVoiceModelManager,
        )

        assert OpenVoiceModelManager is not None

    def test_providers_importable(self) -> None:
        from airunner_services.edge.tts.providers import (
            ESPEAK_CONFIG,
            get_espeak_config,
        )

        assert isinstance(ESPEAK_CONFIG, dict)
        assert callable(get_espeak_config)


class TestEdgeSTT:
    """Verify STT files moved to edge/stt/."""

    def test_faster_whisper_importable(self) -> None:
        from airunner_services.edge.stt.faster_whisper_stt_executor import (
            FasterWhisperSTTExecutor,
        )

        assert FasterWhisperSTTExecutor is not None

    def test_stt_executor_re_exports(self) -> None:
        from airunner_services.edge.stt.stt_executor import STTExecutor
        from airunner_services.shared.interfaces.stt_interface import (
            STTInferenceInterface,
        )

        assert issubclass(STTExecutor, STTInferenceInterface)

    def test_providers_importable(self) -> None:
        from airunner_services.edge.stt.providers import (
            WHISPER_FILES,
            resolve_device,
        )

        assert isinstance(WHISPER_FILES, dict)
        assert callable(resolve_device)


class TestCloudLLM:
    """Verify cloud LLM modules."""

    def test_model_builders_importable(self) -> None:
        from airunner_services.cloud.llm.model_builders import (
            create_openrouter_model,
            create_ollama_model,
            create_openai_model,
        )

        assert callable(create_openrouter_model)
        assert callable(create_ollama_model)
        assert callable(create_openai_model)

    def test_provider_creation_importable(self) -> None:
        from airunner_services.cloud.llm.provider_creation import (
            create_provider_model_from_runtime,
        )

        assert callable(create_provider_model_from_runtime)

    def test_adapters_satisfy_interface(self) -> None:
        from airunner_services.cloud.llm.openrouter_adapter import (
            OpenRouterAdapter,
        )
        from airunner_services.shared.interfaces.llm_interface import (
            LLMInferenceInterface,
        )

        assert issubclass(OpenRouterAdapter, LLMInferenceInterface)


class TestChatModelFactory:
    """Verify ChatModelFactory wires to edge/cloud."""

    def test_factory_importable(self) -> None:
        from airunner_services.llm.adapters.chat_model_factory import (
            ChatModelFactory,
        )

        assert ChatModelFactory is not None


class TestEdgePackage:
    """Verify edge package __all__ matches current state."""

    def test_edge_exports(self) -> None:
        from airunner_services import edge

        exported = set(edge.__all__)
        assert "ChatGGUFAdapter" in exported
        assert "EspeakAdapter" in exported
        assert "OpenVoiceAdapter" in exported
        assert "FasterWhisperAdapter" in exported
        assert "ArtGenerationAdapter" in exported


class TestCloudPackage:
    """Verify cloud package __all__ matches current state."""

    def test_cloud_exports(self) -> None:
        from airunner_services import cloud

        exported = set(cloud.__all__)
        assert "create_openrouter_model" in exported
        assert "create_provider_model_from_runtime" in exported
        assert "OLLAMA_MODELS" in exported
        assert "OPENROUTER_MODELS" in exported
