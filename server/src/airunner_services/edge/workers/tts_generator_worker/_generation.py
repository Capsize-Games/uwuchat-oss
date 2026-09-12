"""TTS generation, daemon synthesis path, and audio decoding."""

from __future__ import annotations

import io
from typing import Optional, Type
from uuid import uuid4

import soundfile as sf

from airunner_services.contract_enums import ModelStatus, TTSModel
from airunner_services.requests.tts_request import EspeakTTSRequest
from airunner_services.requests.tts_request import OpenVoiceTTSRequest
from airunner_services.requests.tts_request import TTSRequest
from airunner_services.settings import AIRUNNER_TTS_MODEL_TYPE
from airunner_services.utils.application.enum_resolver import signal_code_proxy
from airunner_services.utils.text.formatter_extended import FormatterExtended

SignalCode = signal_code_proxy(
    {
        "TTS_GENERATOR_WORKER_ADD_TO_STREAM_SIGNAL": (
            "TTSGeneratorWorker_add_to_stream_signal"
        ),
        "TTS_ENABLE_SIGNAL": "tts_enable_signal",
    }
)


class TTSGeneratorWorkerGenerationMixin:
    """Generate TTS audio locally or via the daemon client."""

    def _log_tts_input(self, message: str) -> None:
        """Log the exact speakable text passed to TTS."""
        log_info = getattr(self.logger, "info", None)
        if not callable(log_info):
            return
        preview = message if len(message) <= 200 else f"{message[:200]}..."
        log_info("TTS input (%d chars): %r", len(message), preview)

    def _sentence_generation_word_threshold(self) -> int:
        """Return the buffered-word threshold before generating speech."""
        default_threshold = self.MIN_WORDS_FOR_GENERATION
        daemon_client_getter = getattr(self, "_daemon_client", None)
        if (
            callable(daemon_client_getter)
            and daemon_client_getter() is not None
        ):
            return self.DAEMON_MIN_WORDS_FOR_GENERATION
        return default_threshold

    def _generate(self, message):
        if self.do_interrupt:
            return
        self.logger.debug("Generating TTS...")

        if isinstance(message, dict):
            message = message.get("message", "")

        message = FormatterExtended.to_speakable_text(message)
        self._log_tts_input(message)

        model = (
            AIRUNNER_TTS_MODEL_TYPE or self.chatbot_voice_settings.model_type
        )

        if model is None:
            self.logger.error("No TTS model found. Skipping generation.")
            return

        model_type = TTSModel(model)

        self.logger.debug(f"self.tts: {self.tts} | model_type: {model_type}")

        response = None
        client = self._daemon_client()
        failed_local_model = (
            model is not None and getattr(self, "_failed_model", None) == model
        )
        current_tts_status = self._current_tts_status()
        if client is None and not failed_local_model:
            needs_local_load = self.tts is None
            if not needs_local_load and hasattr(self.tts, "load"):
                needs_local_load = current_tts_status not in [
                    ModelStatus.LOADED,
                    ModelStatus.LOADING,
                ]
            if needs_local_load:
                self._load_tts()
        if client is not None:
            response = self._generate_via_daemon(message, model)

        tts_req: Optional[Type[TTSRequest]] = None
        if model_type is TTSModel.OPENVOICE:
            tts_req = OpenVoiceTTSRequest(
                message=message,
                gender=self.chatbot.gender,
            )
        elif model_type is TTSModel.ESPEAK:
            tts_req = EspeakTTSRequest(
                message=message,
                gender=self.chatbot.gender,
                rate=self.espeak_settings.rate,
                pitch=self.espeak_settings.pitch,
                volume=self.espeak_settings.volume,
                voice=self.espeak_settings.voice,
                language=self.espeak_settings.language,
            )

        if response is None and self.tts and tts_req and client is None:
            response = self.tts.generate(tts_req)

        if self.do_interrupt:
            return

        if response is not None:
            if self._forward_gui_audio_response(response):
                return
            self.emit_signal(
                SignalCode.TTS_GENERATOR_WORKER_ADD_TO_STREAM_SIGNAL,
                {"message": response},
            )

    def _generate_via_daemon(
        self,
        message: str,
        model_type: Optional[str],
    ):
        client = self._daemon_client()
        if client is None:
            return None
        request_id = str(uuid4())
        self._active_request_id = request_id
        try:
            audio_bytes = client.synthesize_tts(
                message,
                voice=getattr(self.chatbot_voice_settings, "voice", None),
                model=getattr(self.path_settings, "tts_model_path", None),
                model_type=model_type,
                request_id=request_id,
            )
            return self._decode_daemon_audio(audio_bytes)
        except RuntimeError as exc:
            self.logger.error(f"Daemon TTS generation failed: {exc}")
            return None
        finally:
            self._active_request_id = None

    @staticmethod
    def _decode_daemon_audio(audio_bytes: bytes):
        audio, _sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32")
        if getattr(audio, "ndim", 1) > 1:
            return audio[:, 0]
        return audio
