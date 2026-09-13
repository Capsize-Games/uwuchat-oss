"""Extra per-turn context parts: bot weather."""

from __future__ import annotations

from typing import Optional

from airunner_services.contract_enums import LLMActionType
from airunner_services.llm.managers.prompt_builder.prompt_builder import (
    CONVERSATIONAL_ACTIONS,
)


async def bot_weather_part(owner, action: LLMActionType) -> Optional[str]:
    """Return current weather at the chatbot's own location.

    Only injected for the system bot (not RP chatbots) and only
    when the chatbot has use_weather_prompt enabled.
    """
    if action not in CONVERSATIONAL_ACTIONS:
        return None
    chatbot = getattr(owner, "chatbot", None)
    if not chatbot or not getattr(chatbot, "is_system_bot", False):
        return None
    if not getattr(chatbot, "use_weather_prompt", False):
        return None
    location = getattr(chatbot, "location", None) or {}
    lat = location.get("latitude")
    lon = location.get("longitude")
    city = location.get("city", "")
    if not lat or not lon:
        return None
    from airunner_services.downloads.policy import is_openmeteo_allowed

    if not is_openmeteo_allowed():
        return None
    from airunner_services.services.weather_service import fetch_weather_async

    user = getattr(owner, "user", None)
    unit = getattr(user, "unit_system", "imperial") or "imperial"
    weather = await fetch_weather_async(float(lat), float(lon), unit)
    if not weather:
        return None
    t_u = weather["temperature_unit"]
    ws_u = weather["wind_speed_unit"]
    p_u = weather["precipitation_unit"]
    label = (
        f"[My weather right now — {city}]"
        if city
        else "[My weather right now]"
    )
    lines = [label, f"Temperature: {weather['temperature']}{t_u}"]
    if weather["snowfall"] > 0:
        lines.append(f"Snowfall: {weather['snowfall']} {p_u}")
    elif weather["rain"] > 0:
        lines.append(f"Rain: {weather['rain']} {p_u}")
    lines.append(
        f"Wind: {weather['wind_speed']} {ws_u} "
        f"(gusts {weather['wind_gusts']} {ws_u})"
    )
    forecast = weather.get("forecast_text", "")
    if forecast:
        lines.append("")
        lines.append(forecast)
    return "\n".join(lines)
