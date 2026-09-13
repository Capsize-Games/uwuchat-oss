"""Weather mixin for edge/local agent deployments.

Consolidated fetch moved to ``airunner_services.services.weather_service``.
All functions are ≤20 lines.
"""

from __future__ import annotations

from airunner_services.downloads.policy import is_openmeteo_allowed
from airunner_services.services.weather_service import fetch_weather


class WeatherMixin:
    """Mixin providing weather context for edge/local agents."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @property
    def unit_system(self) -> str:
        return self.user.unit_system

    def _weather_guard(self) -> bool:
        """Return True if weather is available (passes all guards)."""
        if not is_openmeteo_allowed():
            return False
        if not self.user.latitude or not self.user.longitude:
            return False
        if not self.chatbot.use_weather_prompt:
            return False
        if not self.llm_settings.use_weather_prompt:
            return False
        return True

    def _weather_prompt_lines(self, weather) -> list[str]:
        t_u = weather["temperature_unit"]
        ws_u = weather["wind_speed_unit"]
        p_u = weather["precipitation_unit"]
        return [
            "Current weather:",
            f"- temperature: {weather['temperature']} {t_u}",
            f"- precipitation: {weather['precipitation']} {p_u}",
            f"- rain: {weather['rain']} {p_u}",
            f"- showers: {weather.get('showers', 0)} {p_u}",
            f"- snowfall: {weather['snowfall']} {p_u}",
            f"- wind speed: {weather['wind_speed']} {ws_u}",
            f"- wind direction: {weather['wind_direction']}",
            f"- wind gusts: {weather['wind_gusts']} {ws_u}",
        ]

    @property
    def weather_prompt(self) -> str:
        if not self._weather_guard():
            return ""
        weather = fetch_weather(
            self.user.latitude, self.user.longitude,
            self.unit_system,
        )
        if not weather:
            return ""
        lines = self._weather_prompt_lines(weather)
        forecast = weather.get("forecast_text", "")
        if forecast:
            lines.append("")
            lines.append(forecast)
        return "\n".join(lines)
