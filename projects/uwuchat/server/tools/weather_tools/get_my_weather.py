"""LLM tool: get_my_weather — full detail for the user's saved location.

All functions are ≤20 lines.
"""

from __future__ import annotations

from typing import Any

from airunner_services.llm.core.tool_registry import ToolCategory, tool
from airunner_services.services.weather_service import fetch_weather


def _weather_line(weather, t_u, ws_u, p_u) -> list[str]:
    label = weather.get("weather_label", "Unknown")
    lines = [
        "Your weather right now:",
        f"- Temperature: {weather['temperature']}{t_u}",
        f"- Conditions: {label}",
        f"- Precipitation: {weather['precipitation']} {p_u}",
    ]
    if weather.get("rain", 0) > 0:
        lines.append(f"- Rain: {weather['rain']} {p_u}")
    if weather.get("snowfall", 0) > 0:
        lines.append(f"- Snowfall: {weather['snowfall']} {p_u}")
    ws = (
        f"{weather['wind_speed']} {ws_u} "
        f"(gusts {weather['wind_gusts']} {ws_u})"
    )
    lines.append(f"- Wind: {ws}")
    return lines


def _format_my_weather(w: dict) -> str:
    lines = _weather_line(
        w, w["temperature_unit"],
        w["wind_speed_unit"], w["precipitation_unit"],
    )
    fct = w.get("forecast_text", "")
    if fct:
        lines += ["", fct]
    lines.append("\nTell the user the weather in your voice.")
    return "\n".join(lines)


@tool(
    name="get_my_weather",
    category=ToolCategory.SYSTEM,
    description="Get weather for the user's saved location.",
    return_direct=False,
    requires_agent=True,
    defer_loading=True,
    keywords=["weather", "forecast", "temperature", "my weather"],
    input_examples=[{}],
)
def get_my_weather(agent: Any = None) -> str:
    user = getattr(agent, "user", None) if agent else None
    if not user:
        return "I'd need to know who you are."
    lat = getattr(user, "latitude", None)
    lon = getattr(user, "longitude", None)
    if not lat or not lon:
        return "You haven't set a location."
    unit = getattr(user, "unit_system", "imperial") or "imperial"
    w = fetch_weather(float(lat), float(lon), unit)
    if not w:
        return "Couldn't reach the forecast service."
    return _format_my_weather(w)
