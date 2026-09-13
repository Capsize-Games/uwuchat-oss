"""Framework-default resource exposure and store-table lookup."""

from __future__ import annotations

import importlib
import re

from airunner_services.api.resource_guards import (
    expose_resource,
    is_exposed,
)

# -- framework default exposed resources --------------------------------
# Resources the desktop/settings UI calls via getSingleton /
# updateSingleton / queryResources / queryFirstResource.  Any second
# AIRunner site's settings UI needs exactly these reachable.

_FRAMEWORK_EXPOSED_RESOURCES = frozenset({
    "ApplicationSettings",
    "Chatbot",
    "EspeakSettings",
    "GeneratorSettings",
    "LanguageSettings",
    "LLMGeneratorSettings",
    "MemorySettings",
    "OpenVoiceSettings",
    "PathSettings",
    "PromptTemplate",
    "ShortcutKeys",
    "SoundSettings",
    "STTSettings",
    "User",
    "VoiceSettings",
})


def register_framework_resources() -> None:
    """Expose the framework-default resources to the WS resource store.

    Called from the package ``__init__`` so importing (or reloading)
    the package (re)runs the allowlist registration.
    """
    for res in _FRAMEWORK_EXPOSED_RESOURCES:
        expose_resource(res)


def resource_store_table(resource_name: str):
    """Return the SQLAlchemy model class for a resource name.

    Raises ``LookupError`` if the resource has not been explicitly
    exposed to the WS resource store — see ``resource_guards.is_exposed``.
    """
    if not is_exposed(resource_name):
        raise LookupError(f"Resource not exposed: {resource_name}")
    snake = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", resource_name)
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", snake)
    snake = snake.lower()
    module_path = f"airunner_services.database.models.{snake}"
    module = importlib.import_module(module_path)
    return getattr(module, resource_name)
