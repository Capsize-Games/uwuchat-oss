"""Extension configuration for the FastSearch extension."""

from airunner_services.extensions.config import ExtensionConfig


class FastSearchExtension(ExtensionConfig):
    """Configuration for the FastSearch search engine integration.

    The ``ready()`` hook imports the tool module to trigger the
    ``@tool`` decorators, which register the search tools with
    ``ToolRegistry`` at server startup.
    """

    name = "fastsearch"
    label = "FastSearch"
    description = (
        "Custom search engine integration for web, images, "
        "videos, news, books, and more"
    )

    def ready(self) -> None:
        """Import tool module to trigger @tool decorator registration.

        This is called by the extension loader during server startup.
        The import fires the ``@tool()`` decorators in ``tools.py``,
        which call ``ToolRegistry.register()`` for each tool.
        """
        import importlib

        importlib.import_module("extensions.fastsearch.server.tools")
