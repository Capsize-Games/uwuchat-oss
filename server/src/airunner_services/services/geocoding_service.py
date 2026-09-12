"""Plaintext-to-coordinates geocoding via Open-Meteo's free API.

No API key required.  Covers the entire world (not just US ZIP codes).
Results are cached for 24 hours.  All functions are ≤20 lines.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

from airunner_services.services.weather_service import GEOCODING_URL

logger = logging.getLogger(__name__)

_GEOCODING_CACHE_EXPIRATION = 86400
_REQUEST_TIMEOUT = 10


def _geocoding_cache_path() -> str:
    base = os.environ.get("AIRUNNER_BASE_PATH", tempfile.gettempdir())
    return os.path.join(
        base, "text", "other", "cache", ".geocoding_cache",
    )


def _get_geocoding_session():
    import requests_cache
    cache_path = _geocoding_cache_path()
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    return requests_cache.CachedSession(
        cache_path, expire_after=_GEOCODING_CACHE_EXPIRATION,
    )


def _format_geocoding_result(results: list[dict]) -> list[dict]:
    return [{
        "name": r.get("name", ""),
        "latitude": r.get("latitude"),
        "longitude": r.get("longitude"),
        "country": r.get("country", ""),
        "admin1": r.get("admin1"),
        "timezone": r.get("timezone", ""),
        "country_code": r.get("country_code", ""),
    } for r in results]


def _log_geocoding_error(exc: Exception, query: str) -> None:
    from airunner_services.utils.network_retry import (
        is_http_service_error,
        is_transient_network_error,
        log_network_failure,
    )
    if is_transient_network_error(exc) or is_http_service_error(exc):
        log_network_failure(
            logger, "Geocoding failed (query=%s)" % query, exc,
        )
    else:
        logger.error(
            "Geocoding failed (query=%s)", query, exc_info=True,
        )


def _get_session_or_fallback():
    import requests
    try:
        return _get_geocoding_session()
    except Exception:
        return requests.Session()


def _do_geocode(query, count, session):
    params = {"name": query, "count": count,
              "language": "en", "format": "json"}
    resp = session.get(
        GEOCODING_URL, params=params, timeout=_REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    return _format_geocoding_result(results[:count])


def geocode_location(
    query: str, count: int = 1,
) -> Optional[list[dict]]:
    try:
        return _do_geocode(query, count, _get_session_or_fallback())
    except Exception as exc:
        _log_geocoding_error(exc, query)
        return None
