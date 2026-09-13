"""Consolidated Open-Meteo weather service.

``fetch_weather`` is the single entry point used by the ambient injector,
RPC endpoint, and LLM weather tools.  Shared constants are importable so
consumers do not duplicate Open-Meteo HTTP logic.  No function exceeds 20
lines (per CLAUDE.md rule).
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

from airunner_services.services.weather_response import (
    daily_array,
    forecast_text,
    hourly_array,
    parse_current,
)

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_CACHE_EXPIRATION = 3600
REQUEST_TIMEOUT = 10


def weather_cache_path() -> str:
    """Return a writable path for the requests_cache SQLite file."""
    base = os.environ.get("AIRUNNER_BASE_PATH", tempfile.gettempdir())
    return os.path.join(base, "text", "other", "cache", ".requests_cache")


# ---------------------------------------------------------------------------
# Cache-hit dedup
# ---------------------------------------------------------------------------

_OBSERVED_LRU: OrderedDict = OrderedDict()
_MAX_OBSERVED = 1000


def _mark_observed(lat: float, lon: float) -> bool:
    """Return True if (lat, lon, hour) was already seen this hour."""
    hour_bucket = int(datetime.now(timezone.utc).timestamp() // 3600)
    key = (round(lat, 2), round(lon, 2), hour_bucket)
    if key in _OBSERVED_LRU:
        _OBSERVED_LRU.move_to_end(key)
        return True
    _OBSERVED_LRU[key] = True
    if len(_OBSERVED_LRU) > _MAX_OBSERVED:
        _OBSERVED_LRU.popitem(last=False)
    return False


# ---------------------------------------------------------------------------
# Session / params helpers
# ---------------------------------------------------------------------------


def _get_cached_session():
    """Return a ``requests_cache.CachedSession`` (1-hour TTL)."""
    import requests_cache
    cache_path = weather_cache_path()
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    return requests_cache.CachedSession(
        cache_path, expire_after=WEATHER_CACHE_EXPIRATION,
    )


def _ws_api_unit(is_metric: bool) -> str:
    """Return the Open-Meteo wind-speed unit string."""
    return "kmh" if is_metric else "mph"


def _current_params() -> str:
    return (
        "temperature_2m,relative_humidity_2m,"
        "apparent_temperature,weather_code,cloud_cover,"
        "precipitation,rain,showers,snowfall,"
        "wind_speed_10m,wind_direction_10m,wind_gusts_10m,"
        "uv_index,is_day"
    )


def _daily_params() -> str:
    return (
        "weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_sum,rain_sum,showers_sum,snowfall_sum,"
        "precipitation_probability_max,wind_speed_10m_max,"
        "wind_gusts_10m_max"
    )


def _hourly_params() -> str:
    return (
        "temperature_2m,weather_code,"
        "precipitation_probability,precipitation,"
        "wind_speed_10m,relative_humidity_2m,"
        "apparent_temperature"
    )


def _build_params(lat: float, lon: float, is_m: bool) -> dict:
    return {
        "latitude": lat, "longitude": lon,
        "current": _current_params(),
        "daily": _daily_params(),
        "hourly": _hourly_params(),
        "temperature_unit": "celsius" if is_m else "fahrenheit",
        "wind_speed_unit": _ws_api_unit(is_m),
        "precipitation_unit": "mm" if is_m else "inch",
        "forecast_days": 10,
    }


# ---------------------------------------------------------------------------
# Result assembly
# ---------------------------------------------------------------------------


def _assemble_result(data, is_metric, temp_label, wind_unit) -> dict:
    """Parse and assemble the full weather response dict."""
    result = parse_current(data, is_metric)
    result["forecast_text"] = forecast_text(data)
    result["daily"] = daily_array(data, temp_label, wind_unit)
    result["hourly"] = hourly_array(data, temp_label, wind_unit)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _do_fetch(lat, lon, is_m, tl, wu, us):
    session = _get_cached_session()
    resp = session.get(OPEN_METEO_URL,
                       params=_build_params(lat, lon, is_m),
                       timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    from_cache = getattr(resp, "from_cache", False)
    result = _assemble_result(resp.json(), is_m, tl, wu)
    if not from_cache and not _mark_observed(lat, lon):
        try:
            _record_weather_observation(lat, lon, result, us)
        except Exception:
            logger.exception(
                "Failed to record weather observation "
                "(lat=%s, lon=%s)",
                lat, lon,
            )
    return result


def fetch_weather(
    lat: float,
    lon: float,
    unit_system: str = "imperial",
) -> Optional[dict]:
    """Fetch current conditions and 10-day forecast from Open-Meteo."""
    is_m = unit_system == "metric"
    temp_label = "°C" if is_m else "°F"
    wind_unit = "km/h" if is_m else "mph"
    try:
        return _do_fetch(lat, lon, is_m, temp_label, wind_unit,
                         unit_system)
    except Exception as exc:
        _log_fetch_error(exc, lat, lon)
        return None


async def fetch_weather_async(
    lat: float,
    lon: float,
    unit_system: str = "imperial",
) -> Optional[dict]:
    """Fetch weather without blocking the event loop."""
    return await asyncio.to_thread(
        fetch_weather, lat, lon, unit_system,
    )


def _observation_kwargs(
    lat: float, lon: float, wd: dict, unit_system: str,
) -> dict:
    """Build kwargs for WeatherObservation.objects.create()."""
    return {
        "observed_at": datetime.now(timezone.utc),
        "latitude": round(lat, 2), "longitude": round(lon, 2),
        "temperature": wd.get("temperature"),
        "precipitation": wd.get("precipitation"),
        "rain": wd.get("rain"), "snowfall": wd.get("snowfall"),
        "wind_speed": wd.get("wind_speed"),
        "wind_gusts": wd.get("wind_gusts"),
        "weather_code": wd.get("weather_code"),
        "unit_system": unit_system, "source": "open-meteo",
    }


def _record_weather_observation(
    lat: float, lon: float,
    weather_data: dict, unit_system: str,
) -> None:
    """Persist an anonymous historical weather observation."""
    from airunner_services.database.models.weather_observation import (
        WeatherObservation,
    )
    WeatherObservation.objects.create(
        **_observation_kwargs(lat, lon, weather_data, unit_system),
    )


def _log_fetch_error(exc: Exception, lat: float, lon: float) -> None:
    """Classify and log a weather-fetch exception.

    DNS resolution failures get a loud, actionable ERROR so the
    operator knows the container may have stale DNS from a Mullvad
    relay switch — re-running ``scripts/docker.sh recreate server``
    will pick up the fresh resolver.
    """
    from airunner_services.utils.network_retry import (
        is_dns_resolution_error,
        is_http_service_error,
        is_transient_network_error,
        log_dns_failure_warning,
        log_network_failure,
    )
    if is_dns_resolution_error(exc):
        log_dns_failure_warning(logger)
        logger.error(
            "Weather fetch failed (lat=%s, lon=%s): %s",
            lat, lon, exc,
        )
    elif is_transient_network_error(exc) or is_http_service_error(exc):
        log_network_failure(
            logger,
            "Weather fetch failed (lat=%s, lon=%s)" % (lat, lon),
            exc,
        )
    else:
        logger.error(
            "Weather fetch failed (lat=%s, lon=%s)",
            lat, lon, exc_info=True,
        )
