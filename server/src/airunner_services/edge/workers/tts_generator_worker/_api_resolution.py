"""Application/API resolution and TTS capability probes."""

from __future__ import annotations

from typing import Optional

from airunner_services.contract_enums import ModelStatus, ModelType
from airunner_services.settings import AIRUNNER_TTS_MODEL_TYPE
from airunner_services.settings import AIRUNNER_TTS_ON
from airunner_services.utils.application import peek_registered_api


class TTSGeneratorWorkerApiResolutionMixin:
    """Resolve live API references and report TTS runtime status."""

    @property
    def tts_enabled(self) -> bool:
        return (
            self.application_settings and self.application_settings.tts_enabled
        ) or AIRUNNER_TTS_ON

    def _current_api(self):
        """Return the freshest API reference available to this worker."""
        candidates = []
        refresher = getattr(self, "refresh_api_reference", None)
        if callable(refresher):
            candidates.append(refresher())
        candidates.append(getattr(self, "api", None))
        resolve_api = getattr(
            self,
            "_resolve_api_instance",
            TTSGeneratorWorkerApiResolutionMixin._resolve_api_instance,
        )
        candidates.append(resolve_api())
        main_window_getter = getattr(
            self,
            "_main_window",
            TTSGeneratorWorkerApiResolutionMixin._main_window,
        )
        candidates.append(main_window_getter())

        fallback_api = None
        for candidate in candidates:
            candidate = self._normalize_api_candidate(candidate)
            if candidate is None or False:
                continue
            if getattr(candidate, "daemon_client", None) is not None:
                self.api = candidate
                return candidate
            if fallback_api is None:
                fallback_api = candidate

        if fallback_api is not None:
            self.api = fallback_api
        return fallback_api

    @staticmethod
    def _normalize_api_candidate(candidate):
        """Return one app-like API object from a nested candidate."""
        if candidate is None:
            return None

        root_api = getattr(candidate, "api", None)
        if (
            root_api is not None
            and getattr(
                candidate,
                "daemon_client",
                None,
            )
            is None
        ):
            return root_api

        app_api = getattr(getattr(candidate, "app", None), "api", None)
        if (
            app_api is not None
            and getattr(
                candidate,
                "daemon_client",
                None,
            )
            is None
        ):
            return app_api
        return candidate

    @staticmethod
    def _resolve_api_instance():
        """Resolve the registered App/API object when worker init ran early."""
        return peek_registered_api()

    @staticmethod
    def _main_window_api():
        """Return the API exposed by the active GUI main window."""
        main_window = TTSGeneratorWorkerApiResolutionMixin._main_window()
        if main_window is None:
            return None
        return getattr(main_window, "api", None) or getattr(
            getattr(main_window, "app", None),
            "api",
            None,
        )

    @staticmethod
    def _main_window():
        """Return the registered GUI main window when one exists."""
        api = TTSGeneratorWorkerApiResolutionMixin._normalize_api_candidate(
            peek_registered_api()
        )
        if api is None:
            return None
        return getattr(api, "main_window", None)

    def _daemon_client(self):
        api = self._current_api()
        if api is None or False:
            return None
        client = getattr(api, "daemon_client", None)
        if client is not None:
            return client

        main_window_getter = getattr(
            self,
            "_main_window",
            TTSGeneratorWorkerApiResolutionMixin._main_window,
        )
        main_window = main_window_getter()
        if main_window is None:
            return None

        worker_manager = getattr(main_window, "worker_manager", None)
        daemon_getter = getattr(worker_manager, "_daemon_client", None)
        if callable(daemon_getter):
            client = daemon_getter()
            if client is not None:
                return client

        for candidate in (
            getattr(main_window, "api", None),
            getattr(getattr(main_window, "app", None), "api", None),
        ):
            candidate = self._normalize_api_candidate(candidate)
            if candidate is None or False:
                continue
            client = getattr(candidate, "daemon_client", None)
            if client is not None:
                return client
        return None

    def _active_tts_model(self) -> Optional[str]:
        """Return the currently selected TTS model name."""
        return (
            AIRUNNER_TTS_MODEL_TYPE or self.chatbot_voice_settings.model_type
        )

    def _has_daemon_tts_capability(self) -> bool:
        """Return whether streamed TTS should use the daemon path."""
        return self._daemon_client() is not None

    def _report_tts_load_error(self, error: Exception) -> None:
        """Surface one local TTS load failure to the application boundary."""
        api = self._current_api()
        reporter = getattr(api, "application_error", None)
        if callable(reporter):
            reporter(error)
            return
        self.logger.error("TTS load failed: %s", error)

    def _current_tts_status(self) -> ModelStatus:
        """Return the active local TTS runtime status."""
        if self.tts is None:
            return ModelStatus.UNLOADED

        status = getattr(self.tts, "status", None)
        if isinstance(status, ModelStatus):
            return status

        model_status = getattr(self.tts, "model_status", None)
        if isinstance(model_status, dict):
            return model_status.get(ModelType.TTS, ModelStatus.UNLOADED)
        if isinstance(model_status, ModelStatus):
            return model_status
        return ModelStatus.UNLOADED
