"""TTS model manager load/unload lifecycle."""

from __future__ import annotations

from airunner_services.contract_enums import TTSModel
from airunner_services.edge.tts.openvoice_exceptions import OpenVoiceError


class TTSGeneratorWorkerModelLifecycleMixin:
    """Manage the local TTS model manager lifecycle."""

    def _reload_tts_model_manager(self, data: dict):
        self.logger.info("Reloading TTS handler...")
        new_model = data.get("model") if data else None
        self.logger.info(
            f"Current model: {self._current_model} | New model: {new_model}"
        )
        if new_model is None or self._current_model == new_model:
            return

        old_tts = self.tts
        self._current_model = new_model
        self._failed_model = None
        self.tts = None

        if old_tts is not None:
            old_tts.unload()

        self._load_tts()

    def on_application_settings_changed_signal(self, data):
        setting_name = data.get("setting_name", "") if data else ""
        column_name = data.get("column_name", "") if data else ""
        value = data.get("val") if data else None
        if value is None and data:
            value = data.get("value")

        if setting_name != "openvoice_settings":
            return

        if self._daemon_client() is not None:
            return

        if column_name != "reference_speaker_path":
            return

        if self.tts and hasattr(self.tts, "reload_speaker_embeddings"):
            self.tts.reload_speaker_embeddings(reference_speaker_path=value)
            return

        if self._active_tts_model() != TTSModel.OPENVOICE.value:
            return

        self._initialize_tts_model_manager()
        if self.tts and hasattr(self.tts, "reload_speaker_embeddings"):
            self.tts.reload_speaker_embeddings(reference_speaker_path=value)
            if self.tts_enabled:
                self._load_tts()

    def _initialize_tts_model_manager(self):
        self.logger.info("Initializing TTS handler...")
        model = self._active_tts_model()
        if model is None:
            self.logger.error("No TTS model found. Skipping initialization.")
            return
        model_type = TTSModel(model)
        if self.tts and self._current_model == model:
            self.logger.debug(
                "TTS model already initialized and matches current model."
            )
            return
        self._current_model = model
        if model_type is TTSModel.OPENVOICE:
            from airunner_services.edge.tts.openvoice_model_manager import (
                OpenVoiceModelManager,
            )

            tts_model_manager_class_ = OpenVoiceModelManager
        else:
            from airunner_services.edge.tts.espeak_model_manager import (
                EspeakModelManager,
            )

            tts_model_manager_class_ = EspeakModelManager
        self.tts = tts_model_manager_class_()
        self.logger.debug(f"Instantiated new TTS model manager: {self.tts}")

    def _load_tts(self):
        if self._daemon_client() is not None:
            return
        if not self.tts_enabled:
            self.logger.info("TTS is disabled. Skipping load.")
            return

        model = self._active_tts_model()
        if model is not None and self._failed_model == model:
            return

        try:
            if not self.tts:
                self.logger.info("Initializing TTS model manager...")
                self._initialize_tts_model_manager()

            if self.tts:
                self.logger.info("Loading TTS model manager...")
                loaded = self.tts.load()
                if loaded is False:
                    self.logger.info(
                        "TTS model manager did not finish loading."
                    )
                    self.tts = None
                    self._failed_model = model
                    return
                self._failed_model = None
        except (FileNotFoundError, ImportError, OpenVoiceError) as error:
            self.tts = None
            self._failed_model = model
            self._report_tts_load_error(error)
        except Exception as error:
            self.tts = None
            self._failed_model = model
            self._report_tts_load_error(error)

    def load(self):
        self._load_tts()

    def unload(self):
        self._unload_tts()

    def _unload_tts(self):
        if self._daemon_client() is not None:
            self._active_request_id = None
            return
        if self.tts:
            self.tts.unload()
