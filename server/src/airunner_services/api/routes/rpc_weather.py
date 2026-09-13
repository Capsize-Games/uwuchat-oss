"""RPC handler: current weather and 10-day forecast.

Consolidated fetch logic lives in
``airunner_services.services.weather_service``;
this module is a thin RPC wrapper that calls ``fetch_weather_async``
and reformats the result into the UI panel response shape.
No function exceeds 20 lines.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from airunner_services.api.routes.events import _rpc_register
from airunner_services.services.weather_service import (
    WEATHER_CACHE_EXPIRATION,
    fetch_weather_async,
)

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = WEATHER_CACHE_EXPIRATION

_weather_cache: dict[
    tuple[int, str], tuple[datetime, dict[str, Any]]
] = {}


def _get_cached_weather(
    account_id: int, unit_system: str,
) -> dict[str, Any] | None:
    """Return cached weather body if still fresh, otherwise None."""
    key = (account_id, unit_system)
    entry = _weather_cache.get(key)
    if entry is None:
        return None
    cached_at, body = entry
    age = (datetime.now(timezone.utc) - cached_at).total_seconds()
    if age >= _CACHE_TTL_SECONDS:
        del _weather_cache[key]
        return None
    return body


def _set_cached_weather(
    account_id: int, unit_system: str, body: dict[str, Any],
) -> None:
    """Store a processed weather body in the in-memory cache."""
    _weather_cache[(account_id, unit_system)] = (
        datetime.now(timezone.utc), body,
    )


def _rpc_current(weather: dict) -> dict:
    return {
        "temperature": weather["temperature"],
        "apparent_temperature": weather.get("apparent_temperature", 0),
        "humidity": weather.get("humidity", 0),
        "weather_code": weather["weather_code"],
        "weather_label": weather["weather_label"],
        "is_day": weather.get("is_day", 1),
        "cloud_cover": weather.get("cloud_cover", 0),
        "uv_index": weather.get("uv_index", 0),
        "precipitation": weather["precipitation"],
        "rain": weather["rain"], "showers": weather.get("showers", 0),
        "snowfall": weather["snowfall"],
        "wind_speed": weather["wind_speed"],
        "wind_direction": weather.get("wind_direction", 0),
        "wind_gusts": weather["wind_gusts"],
    }


def _rpc_units(weather: dict) -> dict:
    """Unit-label fields for the UI response."""
    return {
        "temperature_unit": weather["temperature_unit"],
        "wind_speed_unit": weather["wind_speed_unit"],
        "precipitation_unit": weather["precipitation_unit"],
    }


def _build_rpc_body(weather: dict, loc: str, ca: str) -> dict[str, Any]:
    """Reformat the consolidated weather dict into the UI response shape."""
    body = {"location": loc, "cached_at": ca,
            "cache_ttl": _CACHE_TTL_SECONDS}
    body.update(_rpc_current(weather))
    body.update(_rpc_units(weather))
    body["forecast"] = weather.get("daily", [])
    body["hourly"] = weather.get("hourly", [])
    return body


def _broadcast_weather(account_id: int, body: dict[str, Any]) -> None:
    """Broadcast fresh weather to all subscribed clients."""
    try:
        from airunner_services.api.routes.events_bus import WsEventBus
        from airunner_services.api.routes.events_rpc import (
            EVENT_WEATHER_DATA,
        )
        WsEventBus().broadcast(
            EVENT_WEATHER_DATA,
            {"account_id": account_id, "weather": body},
        )
    except Exception:
        pass


def _auth_error(kw):
    """Return (account_id, None) or (0, error_dict) if auth fails."""
    ws = kw.get("ws")
    if ws is None:
        return 0, {"status": 400,
                    "body": {"error": "WebSocket required"}}
    from airunner_services.api.ws_tenant import resolve_ws_tenant
    _tenant, account_id = resolve_ws_tenant(ws)
    if account_id is None:
        return 0, {"status": 401,
                    "body": {"error": "Authentication required"}}
    return account_id, None


def _load_user(aid):
    from airunner_services.database.models.user import User
    u = User.objects.get(aid)
    if u is None:
        return None, {"status": 404,
                       "body": {"error": "User not found"}}
    return u, None


def _check_location(user):
    """Return (lat, lon, unit, loc_name) or error dict."""
    lat = getattr(user, "latitude", None)
    lon = getattr(user, "longitude", None)
    if not lat or not lon:
        return None, {"status": 400,
                       "body": {"error": "Location not set"}}
    unit = getattr(user, "unit_system", "imperial") or "imperial"
    loc_name = getattr(user, "location_display_name", None) or ""
    return (float(lat), float(lon), unit, loc_name), None


@_rpc_register("GET", "/api/v1/weather")
async def _rpc_get_weather(body: dict, **kw: Any) -> dict[str, Any]:
    account_id, err = _auth_error(kw)
    if err:
        return err
    user, err = _load_user(account_id)
    if err:
        return err
    loc_data, err = _check_location(user)
    if err:
        return err
    lat, lon, unit, loc_name = loc_data
    cached = _get_cached_weather(account_id, unit)
    if cached:
        return {"status": 200, "body": cached}
    weather = await fetch_weather_async(lat, lon, unit)
    if not weather:
        return {"status": 503,
                "body": {"error": "Weather unavailable"}}
    cached_at = datetime.now(timezone.utc).isoformat()
    weather_body = _build_rpc_body(weather, loc_name, cached_at)
    _set_cached_weather(account_id, unit, weather_body)
    _broadcast_weather(account_id, weather_body)
    return {"status": 200, "body": weather_body}
