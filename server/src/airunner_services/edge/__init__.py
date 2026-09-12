"""Edge package — local inference code used only in edge deployments.

This package contains all code that requires local hardware (GPU/CPU),
local model weights, or local-only dependencies (torch, diffusers,
transformers, llama-cpp-python, faster-whisper, etc.).

It is NOT loaded in cloud-only deployments.

Only lightweight adapters and providers are imported eagerly.  Heavy
model managers (EspeakModelManager, OpenVoiceModelManager, etc.) are
available as sub-package imports when needed.
"""

from __future__ import annotations

from airunner_services.edge.art.art_generation_adapter import (
    ArtGenerationAdapter,
)
from airunner_services.edge.llm.chat_gguf_adapter import ChatGGUFAdapter
from airunner_services.edge.stt.faster_whisper_adapter import (
    FasterWhisperAdapter,
)
from airunner_services.edge.tts.espeak_adapter import EspeakAdapter
from airunner_services.edge.tts.openvoice_adapter import OpenVoiceAdapter

__all__ = [
    "ArtGenerationAdapter",
    "ChatGGUFAdapter",
    "EspeakAdapter",
    "FasterWhisperAdapter",
    "OpenVoiceAdapter",
]
