"""RPC handlers: location / geocoding utilities.

Proxies Nominatim (OpenStreetMap) for city→lat/lon lookups.
No API key required; Nominatim is free for reasonable use.
"""

from __future__ import annotations

import logging
from typing import Any

from airunner_services.api.routes.events import _rpc_register

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_USER_AGENT = "UwUChat/1.0 (uwuchat.com)"
_TIMEOUT = 5


@_rpc_register("POST", "/api/v1/geocode/city")
async def _rpc_geocode_city(body: dict, **kw: Any) -> dict[str, Any]:
    """Resolve a city + country string to lat/lon via Nominatim.

    Body: { "city": "Paris", "country": "France" }
    Response 200: { "lat": 48.8566, "lon": 2.3522,
                    "display_name": "Paris, France" }
    Response 422: { "error": "City not found" }
    """
    city = (body.get("city") or "").strip()
    country = (body.get("country") or "").strip()
    if not city:
        return {"status": 422, "body": {"error": "city is required"}}
    query = f"{city}, {country}" if country else city
    try:
        import requests

        resp = requests.get(
            _NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1},
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        results = resp.json()
        if not results:
            return {
                "status": 422,
                "body": {"error": "City not found"},
            }
        top = results[0]
        return {
            "status": 200,
            "body": {
                "lat": float(top["lat"]),
                "lon": float(top["lon"]),
                "display_name": _short_name(top, city, country),
            },
        }
    except Exception:
        logger.exception("Nominatim geocode failed for %r", query)
        return {
            "status": 500,
            "body": {"error": "Geocoding service unavailable"},
        }


@_rpc_register("POST", "/api/v1/geocode/reverse")
async def _rpc_geocode_reverse(body: dict, **kw: Any) -> dict[str, Any]:
    """Resolve lat/lon to a display name via Nominatim reverse geocoding.

    Body: { "lat": 39.6526, "lon": -104.7691 }
    Response 200: { "display_name": "Denver, Colorado, United States" }
    Response 422: { "error": "..." }
    """
    lat = body.get("lat")
    lon = body.get("lon")
    if lat is None or lon is None:
        return {"status": 422, "body": {"error": "lat and lon are required"}}
    try:
        import requests

        resp = requests.get(
            _NOMINATIM_REVERSE_URL,
            params={"lat": lat, "lon": lon, "format": "jsonv2"},
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json()
        if not result or "display_name" not in result:
            return {
                "status": 422,
                "body": {"error": "Location not found"},
            }
        display_name = _short_reverse_name(result)
        return {"status": 200, "body": {"display_name": display_name}}
    except Exception:
        logger.exception("Nominatim reverse geocode failed for %r,%r", lat, lon)
        return {
            "status": 500,
            "body": {"error": "Geocoding service unavailable"},
        }


def _short_reverse_name(result: dict) -> str:
    """Build a concise 'City, State, Country' from Nominatim reverse result."""
    addr = result.get("address", {}) or {}
    city = (
        addr.get("city")
        or addr.get("town")
        or addr.get("village")
        or addr.get("municipality")
        or ""
    )
    state = addr.get("state", "")
    country = addr.get("country", "")
    parts = [p for p in [city, state, country] if p]
    return ", ".join(parts) if parts else result.get("display_name", "Unknown location")


def _short_name(result: dict, city: str, country: str) -> str:
    """Return a concise 'City, State, Country' display name."""
    full = result.get("display_name", "")
    parts = [p.strip() for p in full.split(",")]
    if not parts:
        return f"{city}, {country}" if country else city
    # For US addresses Nominatim returns "City, County, State, Country"
    if country == "United States" and len(parts) >= 3:
        return f"{parts[0]}, {parts[2]}, {country}"
    return f"{parts[0]}, {country}" if country else parts[0]
