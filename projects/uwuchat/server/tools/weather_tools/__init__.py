"""UwUChat weather LLM tools.

Mirrors the ``calendar_tools`` package structure: each submodule is
imported here so the ``@tool`` decorators fire on module load.
"""

from projects.uwuchat.server.tools.weather_tools.get_my_weather import (
    get_my_weather,
)
from projects.uwuchat.server.tools.weather_tools.search_weather import (
    search_weather,
)

__all__ = [
    "get_my_weather",
    "search_weather",
]
