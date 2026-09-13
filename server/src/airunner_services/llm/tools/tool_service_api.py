"""Server-side API facade injected into ``requires_api`` LLM tools.

Historically ``requires_api`` tools received the live GUI ``api`` object
(resolved via ``peek_registered_api()``), which exposed ``.art`` for image
generation plus persisted application settings.  In the server/daemon
architecture ``peek_registered_api()`` always returns ``None`` (the legacy
GUI server was removed), so non-RAG tools like ``generate_image`` got
``api=None`` and failed with "API not available for tool generate_image".

This facade restores a working ``api`` for those tools without depending on
the GUI.  It exposes:

* ``art`` — an :class:`ARTAPIService`, whose ``llm_image_generated`` emits
  ``LLM_IMAGE_PROMPT_GENERATED_SIGNAL`` over the shared (in-process) signal
  mediator that the eagerly-started ``SDWorker`` listens on.
* ``application_settings`` / ``update_application_settings`` — persisted
  settings access inherited from :class:`APIServiceBase`
  (``RuntimeContextMixin``), so tools can read the active image generator
  and adjust working dimensions.
"""

from __future__ import annotations

from airunner_services.api.api_service_base import APIServiceBase
from airunner_services.database.models.application_settings import (
    ApplicationSettings,
)


class ToolServiceAPI(APIServiceBase):
    """Minimal ``api`` object for server-side ``requires_api`` tools."""

    def __init__(self) -> None:
        super().__init__()
        # Lazy import avoids pulling the art service stack at module import.
        from airunner_services.api.services.art_services import ARTAPIService

        self.art = ARTAPIService()

    def update_application_settings(self, **fields: object) -> object:
        """Persist application-settings updates requested by a tool."""
        return self._update_settings_model(ApplicationSettings, **fields)


__all__ = ["ToolServiceAPI"]
