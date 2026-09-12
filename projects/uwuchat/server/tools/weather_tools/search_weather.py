"""LLM tool: search_weather — weather for any place on Earth, one call.

All functions are ≤20 lines.
"""

from __future__ import annotations

from typing import Annotated, Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from airunner_services.services.geocoding_service import geocode_location
from airunner_services.services.weather_service import fetch_weather


def _resolve_location_display(place: dict) -> str:
    parts = [place["name"]]
    if place.get("admin1"):
        parts.append(place["admin1"])
    if place.get("country"):
        parts.append(place["country"])
    return ", ".join(parts)


def _get_user_unit(agent) -> str:
    user = getattr(agent, "user", None) if agent else None
    if user:
        return getattr(user, "unit_system", "imperial") or "imperial"
    return "imperial"


def _search_lines(weather, dn, t_u, ws_u, p_u) -> list[str]:
    wmo = weather.get("weather_label", "Unknown")
    lines = [
        f"Weather in {dn}:",
        f"- Temperature: {weather['temperature']}{t_u}",
        f"- Conditions: {wmo}",
    ]
    ws = (
        f"{weather['wind_speed']} {ws_u} "
        f"(gusts {weather['wind_gusts']} {ws_u})"
    )
    lines.append(f"- Wind: {ws}")
    if weather.get("precipitation", 0) > 0:
        lines.append(f"- Precipitation: {weather['precipitation']} {p_u}")
    return lines


def _format_search_weather(w: dict, dn: str) -> str:
    l = _search_lines(w, dn, w["temperature_unit"],
                      w["wind_speed_unit"], w["precipitation_unit"])
    f = w.get("forecast_text", "")
    return "\n".join(l + (["", f] if f else [])
                     + ["\nRelay the weather in your voice."])


@tool(
    name="search_weather",
    category=ToolCategory.SYSTEM,
    description="Get current weather for any place in the world by name.",
    return_direct=False,
    requires_agent=False,
    defer_loading=True,
    keywords=["weather in", "forecast for", "city weather"],
    input_examples=[
        {"location": "Kyoto"},
        {"location": "Reykjavik, Iceland"},
    ],
)
def search_weather(
    location: Annotated[str, "Place name (e.g. 'Tokyo', 'Paris')."],
    agent: Any = None,
) -> str:
    results = geocode_location(location, count=1)
    if not results:
        return f"Couldn't find '{location}'. Try a different name?"
    place = results[0]
    dn = _resolve_location_display(place)
    weather = fetch_weather(
        place["latitude"], place["longitude"], _get_user_unit(agent),
    )
    if not weather:
        return f"Found {dn} but couldn't get weather data."
    return _format_search_weather(weather, dn)
